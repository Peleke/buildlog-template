"""Tests for rule-level attribution in the gauntlet review system."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from buildlog.seeds import SeedFile, SeedRule, build_rule_id_index, get_rule_id


class TestGetRuleId:
    """Tests for get_rule_id()."""

    def test_uses_provenance_id_when_present(self):
        rule = SeedRule(
            rule="Test rule",
            category="security",
            context="ctx",
            antipattern="anti",
            rationale="why",
            provenance={"id": "custom-id-123"},
        )
        assert get_rule_id(rule, "security_karen", 0) == "custom-id-123"

    def test_falls_back_to_persona_index(self):
        rule = SeedRule(
            rule="Test rule",
            category="security",
            context="ctx",
            antipattern="anti",
            rationale="why",
        )
        assert get_rule_id(rule, "security_karen", 3) == "security_karen:rule:3"

    def test_falls_back_when_provenance_has_no_id(self):
        rule = SeedRule(
            rule="Test rule",
            category="security",
            context="ctx",
            antipattern="anti",
            rationale="why",
            provenance={"source_id": "q-1", "confidence": 0.8},
        )
        assert get_rule_id(rule, "observer", 0) == "observer:rule:0"

    def test_falls_back_when_provenance_id_not_string(self):
        rule = SeedRule(
            rule="Test rule",
            category="security",
            context="ctx",
            antipattern="anti",
            rationale="why",
            provenance={"id": 42},
        )
        assert get_rule_id(rule, "persona", 1) == "persona:rule:1"

    def test_deterministic_across_calls(self):
        rule = SeedRule(
            rule="Test rule",
            category="security",
            context="ctx",
            antipattern="anti",
            rationale="why",
        )
        id1 = get_rule_id(rule, "persona", 5)
        id2 = get_rule_id(rule, "persona", 5)
        assert id1 == id2 == "persona:rule:5"


class TestBuildRuleIdIndex:
    """Tests for build_rule_id_index()."""

    def test_builds_index_from_multiple_personas(self):
        seeds = {
            "karen": SeedFile(
                persona="karen",
                version=1,
                rules=[
                    SeedRule(
                        rule="Rule A",
                        category="security",
                        context="",
                        antipattern="",
                        rationale="",
                    ),
                    SeedRule(
                        rule="Rule B",
                        category="testing",
                        context="",
                        antipattern="",
                        rationale="",
                    ),
                ],
            ),
            "terror": SeedFile(
                persona="terror",
                version=1,
                rules=[
                    SeedRule(
                        rule="Rule C",
                        category="testing",
                        context="",
                        antipattern="",
                        rationale="",
                    ),
                ],
            ),
        }
        index = build_rule_id_index(seeds)

        assert len(index) == 3
        assert "karen:rule:0" in index
        assert "karen:rule:1" in index
        assert "terror:rule:0" in index

        assert index["karen:rule:0"]["persona"] == "karen"
        assert index["karen:rule:0"]["rule_text"] == "Rule A"
        assert index["karen:rule:0"]["category"] == "security"
        assert index["karen:rule:0"]["index"] == 0

    def test_uses_provenance_id_in_index(self):
        seeds = {
            "p": SeedFile(
                persona="p",
                version=1,
                rules=[
                    SeedRule(
                        rule="Rule X",
                        category="arch",
                        context="",
                        antipattern="",
                        rationale="",
                        provenance={"id": "custom-x"},
                    ),
                ],
            ),
        }
        index = build_rule_id_index(seeds)
        assert "custom-x" in index
        assert "p:rule:0" not in index

    def test_empty_seeds(self):
        assert build_rule_id_index({}) == {}


class TestGauntletPromptRuleIds:
    """Tests that generate_gauntlet_prompt includes rule IDs."""

    def test_prompt_contains_rule_ids(self, tmp_path, monkeypatch):
        """Prompt should show [rule_id] next to each rule."""
        import yaml

        from buildlog.core.operations import generate_gauntlet_prompt

        seeds_dir = tmp_path / ".buildlog" / "seeds"
        seeds_dir.mkdir(parents=True)
        seed_data = {
            "persona": "test_persona",
            "version": 1,
            "rules": [
                {
                    "rule": "Always validate input",
                    "category": "security",
                    "context": "user input",
                    "antipattern": "trusting raw",
                    "rationale": "injection prevention",
                },
                {
                    "rule": "Use HTTPS",
                    "category": "security",
                    "context": "network",
                    "antipattern": "HTTP",
                    "rationale": "encryption",
                },
            ],
        }
        with open(seeds_dir / "test_persona.yaml", "w") as f:
            yaml.dump(seed_data, f)

        monkeypatch.chdir(tmp_path)

        result = generate_gauntlet_prompt(target="src/", personas=["test_persona"])
        assert result.error is None
        assert "[test_persona:rule:0]" in result.prompt
        assert "[test_persona:rule:1]" in result.prompt
        assert "rules_consulted" in result.prompt
        assert "rule_reasoning" in result.prompt
        assert "carpet-cite" in result.prompt

    def test_prompt_uses_provenance_id(self, tmp_path, monkeypatch):
        """Prompt should use provenance ID when available."""
        import yaml

        from buildlog.core.operations import generate_gauntlet_prompt

        seeds_dir = tmp_path / ".buildlog" / "seeds"
        seeds_dir.mkdir(parents=True)
        seed_data = {
            "persona": "test_p",
            "version": 1,
            "rules": [
                {
                    "rule": "Some rule",
                    "category": "arch",
                    "provenance": {"id": "my-custom-id"},
                },
            ],
        }
        with open(seeds_dir / "test_p.yaml", "w") as f:
            yaml.dump(seed_data, f)

        monkeypatch.chdir(tmp_path)

        result = generate_gauntlet_prompt(target="src/", personas=["test_p"])
        assert "[my-custom-id]" in result.prompt


class TestGauntletLoopConfigRuleIndex:
    """Tests that gauntlet_loop_config builds and includes rule_id_index."""

    def test_config_includes_rule_id_index(self, tmp_path, monkeypatch):
        import yaml

        from buildlog.core.operations import gauntlet_loop_config

        seeds_dir = tmp_path / ".buildlog" / "seeds"
        seeds_dir.mkdir(parents=True)
        seed_data = {
            "persona": "test_reviewer",
            "version": 1,
            "rules": [
                {
                    "rule": "Check boundaries",
                    "category": "security",
                    "context": "input",
                    "antipattern": "no validation",
                    "rationale": "safety",
                },
            ],
        }
        with open(seeds_dir / "test_reviewer.yaml", "w") as f:
            yaml.dump(seed_data, f)

        monkeypatch.chdir(tmp_path)

        result = gauntlet_loop_config(target="src/")
        assert result.error is None
        assert "test_reviewer:rule:0" in result.rule_id_index
        entry = result.rule_id_index["test_reviewer:rule:0"]
        assert entry["persona"] == "test_reviewer"
        assert entry["rule_text"] == "Check boundaries"

    def test_config_rules_have_provenance_id(self, tmp_path, monkeypatch):
        import yaml

        from buildlog.core.operations import gauntlet_loop_config

        seeds_dir = tmp_path / ".buildlog" / "seeds"
        seeds_dir.mkdir(parents=True)
        seed_data = {
            "persona": "test_p",
            "version": 1,
            "rules": [
                {
                    "rule": "Rule one",
                    "category": "testing",
                    "context": "",
                    "antipattern": "",
                    "rationale": "",
                },
            ],
        }
        with open(seeds_dir / "test_p.yaml", "w") as f:
            yaml.dump(seed_data, f)

        monkeypatch.chdir(tmp_path)

        result = gauntlet_loop_config(target="src/")
        rules = result.rules_by_persona["test_p"]
        assert rules[0]["provenance_id"] == "test_p:rule:0"


class TestGauntletProcessIssuesCitations:
    """Tests for citation validation in gauntlet_process_issues."""

    def _setup_buildlog(self, tmp_path: Path) -> Path:
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()
        return buildlog_dir

    def test_validates_citations_strips_hallucinated(self, tmp_path):
        from buildlog.core.operations import gauntlet_process_issues

        buildlog_dir = self._setup_buildlog(tmp_path)
        issues = [
            {
                "severity": "major",
                "category": "security",
                "description": "SQL injection",
                "rule_learned": "Parameterize SQL",
                "rules_consulted": ["karen:rule:0", "fake:rule:99"],
                "rule_reasoning": {
                    "karen:rule:0": "This applies because...",
                    "fake:rule:99": "Hallucinated reasoning",
                },
            },
        ]
        valid_ids = {"karen:rule:0", "karen:rule:1"}

        result = gauntlet_process_issues(
            buildlog_dir, issues, iteration=1, valid_rule_ids=valid_ids
        )

        # Hallucinated ID should be stripped
        assert issues[0]["rules_consulted"] == ["karen:rule:0"]
        assert "fake:rule:99" not in issues[0].get("rule_reasoning", {})

        # Stats should reflect validation
        assert result.citation_stats["total_citations"] == 2
        assert result.citation_stats["valid_citations"] == 1
        assert result.citation_stats["hallucinated_citations"] == 1
        assert result.citation_stats["issues_with_citations"] == 1

        # Credited rules
        assert result.rules_credited == ["karen:rule:0"]

    def test_no_validation_when_valid_rule_ids_none(self, tmp_path):
        from buildlog.core.operations import gauntlet_process_issues

        buildlog_dir = self._setup_buildlog(tmp_path)
        issues = [
            {
                "severity": "minor",
                "category": "style",
                "description": "Long line",
                "rule_learned": "Limit lines",
                "rules_consulted": ["any:rule:0"],
            },
        ]

        result = gauntlet_process_issues(buildlog_dir, issues, iteration=1)

        # All citations trusted when no validation
        assert result.citation_stats["valid_citations"] == 1
        assert result.citation_stats["hallucinated_citations"] == 0
        assert result.rules_credited == ["any:rule:0"]

    def test_backward_compat_no_rules_consulted(self, tmp_path):
        from buildlog.core.operations import gauntlet_process_issues

        buildlog_dir = self._setup_buildlog(tmp_path)
        issues = [
            {
                "severity": "critical",
                "category": "security",
                "description": "Vuln",
                "rule_learned": "Fix vuln",
            },
        ]

        result = gauntlet_process_issues(
            buildlog_dir,
            issues,
            iteration=1,
            valid_rule_ids={"some:rule:0"},
        )

        assert result.action == "fix_criticals"
        assert result.rules_credited == []
        assert result.citation_stats["issues_without_citations"] == 1
        assert result.citation_stats["issues_with_citations"] == 0

    def test_empty_issues_returns_clean_with_empty_stats(self, tmp_path):
        from buildlog.core.operations import gauntlet_process_issues

        buildlog_dir = self._setup_buildlog(tmp_path)

        result = gauntlet_process_issues(
            buildlog_dir, [], iteration=1, valid_rule_ids={"rule:0"}
        )

        assert result.action == "clean"
        assert result.rules_credited == []
        assert result.citation_stats["total_citations"] == 0

    def test_multiple_issues_aggregate_credited_rules(self, tmp_path):
        from buildlog.core.operations import gauntlet_process_issues

        buildlog_dir = self._setup_buildlog(tmp_path)
        issues = [
            {
                "severity": "major",
                "category": "security",
                "description": "Issue 1",
                "rule_learned": "Rule 1",
                "rules_consulted": ["karen:rule:0", "karen:rule:1"],
            },
            {
                "severity": "minor",
                "category": "testing",
                "description": "Issue 2",
                "rule_learned": "Rule 2",
                "rules_consulted": ["karen:rule:1", "terror:rule:0"],
            },
        ]
        valid_ids = {"karen:rule:0", "karen:rule:1", "terror:rule:0"}

        result = gauntlet_process_issues(
            buildlog_dir, issues, iteration=1, valid_rule_ids=valid_ids
        )

        # All three unique valid rule IDs should be credited
        assert set(result.rules_credited) == {
            "karen:rule:0",
            "karen:rule:1",
            "terror:rule:0",
        }
        assert result.citation_stats["total_citations"] == 4
        assert result.citation_stats["valid_citations"] == 4
        assert result.citation_stats["hallucinated_citations"] == 0

    def test_hallucination_logged_as_mistake(self, tmp_path):
        from buildlog.core.operations import gauntlet_process_issues

        buildlog_dir = self._setup_buildlog(tmp_path)
        issues = [
            {
                "severity": "major",
                "category": "security",
                "description": "Issue",
                "rule_learned": "Rule",
                "rules_consulted": ["valid:rule:0", "hallucinated:rule:99"],
            },
        ]

        with patch("buildlog.core.operations.log_mistake") as mock_log:
            gauntlet_process_issues(
                buildlog_dir,
                issues,
                iteration=1,
                valid_rule_ids={"valid:rule:0"},
            )
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs[1]["error_class"] == "citation_hallucination"
            assert "hallucinated:rule:99" in call_kwargs[1]["description"]
            assert call_kwargs[1]["severity"] == "minor"


class TestGauntletProcessIssuesBanditCredit:
    """Tests for per-rule bandit credit (Touch 3)."""

    def _setup_buildlog(self, tmp_path: Path) -> Path:
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()
        return buildlog_dir

    def test_bandit_updated_for_credited_rules(self, tmp_path):
        from buildlog.core.bandit import ThompsonSamplingBandit
        from buildlog.core.operations import gauntlet_process_issues

        buildlog_dir = self._setup_buildlog(tmp_path)
        issues = [
            {
                "severity": "major",
                "category": "security",
                "description": "Issue",
                "rule_learned": "Rule",
                "rules_consulted": ["karen:rule:0"],
            },
        ]

        gauntlet_process_issues(
            buildlog_dir,
            issues,
            iteration=1,
            valid_rule_ids={"karen:rule:0"},
        )

        # Verify bandit state was updated
        # Context is None → "general" (shared pool for all gauntlet rules)
        bandit = ThompsonSamplingBandit(buildlog_dir / "bandit_state.jsonl")
        params = bandit.state.get_params("general", "karen:rule:0")
        assert params is not None
        # After reward=1.0: alpha should be > 1.0 (prior is 1.0)
        assert params.alpha > 1.0

    def test_no_bandit_update_without_citations(self, tmp_path):
        from buildlog.core.operations import gauntlet_process_issues

        buildlog_dir = self._setup_buildlog(tmp_path)
        issues = [
            {
                "severity": "major",
                "category": "security",
                "description": "Issue",
                "rule_learned": "Rule",
            },
        ]

        gauntlet_process_issues(buildlog_dir, issues, iteration=1)

        # Bandit state file should not exist (no updates)
        bandit_path = buildlog_dir / "bandit_state.jsonl"
        assert not bandit_path.exists()

    def test_bandit_failure_doesnt_break_loop(self, tmp_path):
        from buildlog.core.operations import gauntlet_process_issues

        buildlog_dir = self._setup_buildlog(tmp_path)
        issues = [
            {
                "severity": "major",
                "category": "security",
                "description": "Issue",
                "rule_learned": "Rule",
                "rules_consulted": ["karen:rule:0"],
            },
        ]

        with patch("buildlog.core.bandit.ThompsonSamplingBandit") as mock_bandit_cls:
            mock_bandit_cls.side_effect = RuntimeError("bandit broken")
            result = gauntlet_process_issues(
                buildlog_dir,
                issues,
                iteration=1,
                valid_rule_ids={"karen:rule:0"},
            )

        # Should still return valid result despite bandit failure
        assert result.action == "checkpoint_majors"
        assert result.rules_credited == ["karen:rule:0"]


class TestMCPWrapperValidRuleIds:
    """Tests for the MCP wrapper's valid_rule_ids parameter."""

    def test_passes_valid_rule_ids_as_set(self, tmp_path):
        from buildlog.mcp.tools import buildlog_gauntlet_issues

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        issues = [
            {
                "severity": "minor",
                "category": "style",
                "description": "Issue",
                "rule_learned": "Rule",
                "rules_consulted": ["valid:rule:0", "fake:rule:1"],
            },
        ]

        result = buildlog_gauntlet_issues(
            issues=issues,
            iteration=1,
            buildlog_dir=str(buildlog_dir),
            valid_rule_ids=["valid:rule:0"],
        )

        assert result["rules_credited"] == ["valid:rule:0"]
        assert result["citation_stats"]["valid_citations"] == 1
        assert result["citation_stats"]["hallucinated_citations"] == 1

    def test_none_valid_rule_ids_skips_validation(self, tmp_path):
        from buildlog.mcp.tools import buildlog_gauntlet_issues

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        issues = [
            {
                "severity": "minor",
                "category": "style",
                "description": "Issue",
                "rule_learned": "Rule",
                "rules_consulted": ["any:rule:0"],
            },
        ]

        result = buildlog_gauntlet_issues(
            issues=issues,
            iteration=1,
            buildlog_dir=str(buildlog_dir),
        )

        # Should trust all citations
        assert result["rules_credited"] == ["any:rule:0"]
        assert result["citation_stats"]["hallucinated_citations"] == 0

    def test_error_response_includes_new_fields(self):
        from buildlog.mcp.tools import buildlog_gauntlet_issues

        # Neither issues nor issues_file provided
        result = buildlog_gauntlet_issues(iteration=1)

        assert "error" in result
        assert result["rules_credited"] == []
        assert result["citation_stats"] == {}
