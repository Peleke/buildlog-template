"""Tests for closed-loop gauntlet learning (issue #138).

Tests the bridge between gauntlet rule loading and the learning backend:
- select_gauntlet_rules() bridge function
- generate_gauntlet_prompt() with select_k
- gauntlet_loop_config() with select_k
- Full feedback loop: credit → selection shift
- Backwards compatibility: select_k=None = current behavior
"""

from __future__ import annotations

import random
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from buildlog.core.bandit import ThompsonSamplingBandit
from buildlog.core.learning import BuiltinBandit, get_learning_backend
from buildlog.core.operations import (
    gauntlet_loop_config,
    gauntlet_process_issues,
    generate_gauntlet_prompt,
    select_gauntlet_rules,
)
from buildlog.seeds import SeedFile, SeedReference, SeedRule, get_rule_id

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def seeded_random():
    random.seed(42)
    yield
    random.seed()


def _make_seed_file(persona: str, n_rules: int) -> SeedFile:
    """Create a SeedFile with n_rules numbered rules."""
    rules = []
    for i in range(n_rules):
        rules.append(
            SeedRule(
                rule=f"Rule {i} for {persona}",
                category="testing" if i % 2 == 0 else "security",
                context=f"Context for rule {i}",
                antipattern=f"Antipattern {i}",
                rationale=f"Rationale {i}",
                tags=[persona, f"tag-{i}"],
            )
        )
    return SeedFile(persona=persona, version=1, rules=rules)


def _make_seeds(personas: dict[str, int]) -> dict[str, SeedFile]:
    """Create seed dict: {"persona_name": SeedFile(n_rules)}."""
    return {name: _make_seed_file(name, count) for name, count in personas.items()}


# ---------------------------------------------------------------------------
# Layer 0: Unit — select_gauntlet_rules()
# ---------------------------------------------------------------------------


class TestSelectGauntletRules:
    def test_returns_subset_of_rules(self, temp_dir, seeded_random):
        seeds = _make_seeds({"security_karen": 20})
        result = select_gauntlet_rules(temp_dir, seeds, select_k=5)
        assert len(result["security_karen"].rules) == 5

    def test_returns_all_when_k_exceeds_total(self, temp_dir):
        seeds = _make_seeds({"security_karen": 5})
        result = select_gauntlet_rules(temp_dir, seeds, select_k=100)
        assert len(result["security_karen"].rules) == 5

    def test_preserves_persona_metadata(self, temp_dir, seeded_random):
        seeds = _make_seeds({"security_karen": 10})
        result = select_gauntlet_rules(temp_dir, seeds, select_k=3)

        for rule in result["security_karen"].rules:
            assert rule.category in ("testing", "security")
            assert rule.antipattern
            assert rule.context

    def test_seed_rule_ids_passed_to_backend(self, temp_dir, seeded_random):
        """Verify the backend.select() receives seed_rule_ids."""
        seeds = _make_seeds({"persona_a": 10})
        with patch("buildlog.core.operations.get_learning_backend") as mock_factory:
            mock_backend = mock_factory.return_value
            # Return first 3 rule IDs
            all_ids = [
                get_rule_id(r, "persona_a", i)
                for i, r in enumerate(seeds["persona_a"].rules)
            ]
            mock_backend.select.return_value = all_ids[:3]

            select_gauntlet_rules(temp_dir, seeds, select_k=3)

            call_kwargs = mock_backend.select.call_args[1]
            assert call_kwargs["seed_rule_ids"] == set(all_ids)
            assert call_kwargs["context"] is None

    def test_context_is_none_for_global_credit(self, temp_dir, seeded_random):
        """Context must be None so credits from gauntlet_process_issues match."""
        seeds = _make_seeds({"test_terrorist": 10, "security_karen": 10})
        with patch("buildlog.core.operations.get_learning_backend") as mock_factory:
            mock_backend = mock_factory.return_value
            # Just return whatever candidates are passed
            mock_backend.select.side_effect = lambda candidates, **kw: candidates[
                : kw.get("k", 3)
            ]

            select_gauntlet_rules(temp_dir, seeds, select_k=3)

            contexts = [
                call[1]["context"] for call in mock_backend.select.call_args_list
            ]
            assert all(c is None for c in contexts)

    def test_flat_mode_skips_selection(self, temp_dir):
        seeds = _make_seeds({"persona_a": 10})
        result = select_gauntlet_rules(temp_dir, seeds, select_k=None)
        assert result is seeds  # Same object, untouched

    def test_rule_ids_are_stable(self, temp_dir):
        seeds = _make_seeds({"persona_a": 5})
        ids_1 = [
            get_rule_id(r, "persona_a", i)
            for i, r in enumerate(seeds["persona_a"].rules)
        ]
        ids_2 = [
            get_rule_id(r, "persona_a", i)
            for i, r in enumerate(seeds["persona_a"].rules)
        ]
        assert ids_1 == ids_2

    def test_empty_seeds_no_crash(self, temp_dir):
        result = select_gauntlet_rules(temp_dir, {}, select_k=5)
        assert result == {}

    def test_fallback_when_select_returns_empty(self, temp_dir):
        seeds = _make_seeds({"persona_a": 10})
        with patch("buildlog.core.operations.get_learning_backend") as mock_factory:
            mock_backend = mock_factory.return_value
            mock_backend.select.return_value = []

            result = select_gauntlet_rules(temp_dir, seeds, select_k=3)
            # Should fall back to all rules
            assert len(result["persona_a"].rules) == 10


# ---------------------------------------------------------------------------
# Layer 1: Integration — Feedback Loop
# ---------------------------------------------------------------------------


class TestFeedbackLoop:
    def test_credited_rules_get_higher_posterior(self, temp_dir):
        """Credit a rule → its alpha should increase in bandit state."""
        backend = get_learning_backend(temp_dir)
        rule_id = "test_terrorist:rule:0"

        # Simulate gauntlet credit
        backend.update(rule_id, reward=1.0, context="test_terrorist")

        stats = backend.get_stats(context="test_terrorist")
        assert stats[rule_id]["alpha"] > 1.0

    def test_credited_rules_selected_more_often(self, temp_dir):
        """Rules with credit should be selected more than uncredited."""
        seeds = _make_seeds({"persona_a": 10})
        backend = get_learning_backend(temp_dir)

        # Credit rule 0 heavily
        rule_ids = [
            get_rule_id(r, "persona_a", i)
            for i, r in enumerate(seeds["persona_a"].rules)
        ]
        for _ in range(20):
            backend.update(rule_ids[0], reward=1.0, context="persona_a")

        # Run many selections and count
        counts: dict[str, int] = {rid: 0 for rid in rule_ids}
        for _ in range(100):
            selected = backend.select(
                candidates=rule_ids,
                context="persona_a",
                k=3,
                seed_rule_ids=set(rule_ids),
            )
            for s in selected:
                counts[s] += 1

        # Credited rule should appear more than average
        avg = 100 * 3 / len(rule_ids)
        assert counts[rule_ids[0]] > avg

    def test_prompt_shrinks_after_learning(self, temp_dir):
        """After crediting some rules, prompt with select_k should be smaller."""
        seeds_dir = temp_dir / "data" / "seeds"
        seeds_dir.mkdir(parents=True)

        # Write a seed YAML
        import yaml

        seed_data = {
            "persona": "test_persona",
            "version": 1,
            "rules": [
                {
                    "rule": f"Test rule {i}",
                    "category": "testing",
                    "context": f"Context {i}",
                    "antipattern": f"Anti {i}",
                    "rationale": f"Reason {i}",
                }
                for i in range(20)
            ],
        }
        (seeds_dir / "test_persona.yaml").write_text(yaml.dump(seed_data))

        with patch("buildlog.seeds.get_default_seeds_dir", return_value=seeds_dir):
            # Prompt without selection (all rules)
            full = generate_gauntlet_prompt(target="src/")
            full_lines = full.prompt.count("\n")

            # Prompt with selection (top 5)
            ranked = generate_gauntlet_prompt(
                target="src/",
                buildlog_dir=temp_dir,
                select_k=5,
            )
            ranked_lines = ranked.prompt.count("\n")

            assert ranked_lines < full_lines
            assert ranked.total_rules == 5
            assert full.total_rules == 20


# ---------------------------------------------------------------------------
# Layer 3: Statistical — Convergence
# ---------------------------------------------------------------------------


class TestConvergence:
    def test_thompson_sampling_converges(self, temp_dir):
        """Simulate gauntlet cycles: cited rules should dominate selection."""
        seeds = _make_seeds({"persona": 10})
        backend = get_learning_backend(temp_dir)
        rule_ids = [
            get_rule_id(r, "persona", i) for i, r in enumerate(seeds["persona"].rules)
        ]

        # Rules 0-2 are "good" (always cited), rest are "bad"
        good_rules = set(rule_ids[:3])

        # Simulate 30 gauntlet cycles
        for _ in range(30):
            for rid in good_rules:
                backend.update(rid, reward=1.0, context="persona")
            for rid in rule_ids[3:]:
                backend.update(rid, reward=0.0, context="persona")

        # Now select top 3 — should overwhelmingly be the good rules
        hits = 0
        trials = 50
        for _ in range(trials):
            selected = backend.select(
                candidates=rule_ids,
                context="persona",
                k=3,
                seed_rule_ids=set(rule_ids),
            )
            if set(selected) == good_rules:
                hits += 1

        # Should converge >80% of the time after 30 cycles
        assert hits / trials > 0.8

    def test_cold_start_graceful(self, temp_dir):
        """Fresh project with no bandit state should work fine."""
        seeds = _make_seeds({"persona": 5})
        result = select_gauntlet_rules(temp_dir, seeds, select_k=3)
        assert len(result["persona"].rules) == 3


# ---------------------------------------------------------------------------
# Layer 4: Backwards Compatibility
# ---------------------------------------------------------------------------


class TestBackwardsCompat:
    def test_flat_mode_identical_to_current(self, temp_dir):
        """select_k=None should produce the exact same seeds dict."""
        seeds = _make_seeds({"a": 5, "b": 3})
        result = select_gauntlet_rules(temp_dir, seeds, select_k=None)
        assert result is seeds

    def test_no_state_file_works(self, temp_dir):
        """Fresh buildlog_dir with no bandit_state.jsonl → still works."""
        seeds = _make_seeds({"persona": 10})
        result = select_gauntlet_rules(temp_dir, seeds, select_k=5)
        assert len(result["persona"].rules) == 5

    def test_zero_selected_fallback(self, temp_dir):
        """If backend returns empty selection, fall back to all rules."""
        seeds = _make_seeds({"persona": 10})
        with patch("buildlog.core.operations.get_learning_backend") as mock_factory:
            mock_backend = mock_factory.return_value
            mock_backend.select.return_value = []

            result = select_gauntlet_rules(temp_dir, seeds, select_k=5)
            assert len(result["persona"].rules) == 10
