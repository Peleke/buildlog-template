#!/usr/bin/env python3
"""Demo: closed-loop gauntlet learning in action.

Run this to watch rules adapt in real time. Simulates 5 gauntlet cycles
where the same 3 rules keep getting cited. After each cycle, shows:
- Rules in prompt (count)
- Top 5 bandit arms by posterior mean
- Whether the cited rules are rising to the top

Usage:
    python tests/e2e/demo_learning_loop.py
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import yaml

from buildlog.core.learning import get_learning_backend
from buildlog.core.operations import (
    gauntlet_process_issues,
    generate_gauntlet_prompt,
    select_gauntlet_rules,
)
from buildlog.seeds import SeedFile, get_rule_id, load_all_seeds

_VULN_CLASSES = ["SQL injection", "XSS", "CSRF", "auth", "crypto"]


def _vuln_class(i: int) -> str:
    return _VULN_CLASSES[min(i // 3, len(_VULN_CLASSES) - 1)]


def setup_project(base_dir: Path) -> Path:
    """Create a minimal buildlog project with seed rules."""
    buildlog_dir = base_dir / "buildlog"
    buildlog_dir.mkdir()
    seeds_dir = buildlog_dir / ".buildlog" / "seeds"
    seeds_dir.mkdir(parents=True)

    # Create 15 security rules
    rules = []
    for i in range(15):
        rules.append(
            {
                "rule": (f"Security rule {i}: " f"{_vuln_class(i)} check #{i}"),
                "category": "security",
                "context": f"When reviewing security aspect {i}",
                "antipattern": f"Ignoring security check {i}",
                "rationale": f"Prevents vulnerability class {i}",
                "tags": ["security", f"vuln-{i}"],
            }
        )

    seed_data = {"persona": "security_karen", "version": 1, "rules": rules}
    (seeds_dir / "security_karen.yaml").write_text(
        yaml.dump(seed_data, default_flow_style=False)
    )

    return buildlog_dir


def simulate_review(buildlog_dir: Path, seeds: dict, cited_rule_ids: list[str]):
    """Simulate a gauntlet review that cites specific rules."""
    issues = []
    for rid in cited_rule_ids:
        issues.append(
            {
                "severity": "major",
                "category": "security",
                "description": f"Found violation of {rid}",
                "rule_learned": f"Always check {rid}",
                "location": "src/app.py:42",
                "rules_consulted": [rid],
                "rule_reasoning": {rid: "Directly applies to this code"},
            }
        )

    gauntlet_process_issues(
        buildlog_dir=buildlog_dir,
        issues=issues,
        iteration=1,
        source="demo",
        valid_rule_ids=set(cited_rule_ids),
    )


def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        buildlog_dir = setup_project(base_dir)
        seeds_dir = buildlog_dir / ".buildlog" / "seeds"

        print("=" * 70)
        print("  DEMO: Closed-Loop Gauntlet Learning")
        print("=" * 70)
        print()

        # Load seeds and get rule IDs
        seeds = load_all_seeds(seeds_dir)
        sf = seeds["security_karen"]
        all_rule_ids = [
            get_rule_id(r, "security_karen", i) for i, r in enumerate(sf.rules)
        ]

        # These 3 rules will always be cited (the "good" rules)
        cited_ids = all_rule_ids[:3]
        print(f"Total rules: {len(all_rule_ids)}")
        print(f"Rules that will be cited every cycle: {cited_ids}")
        print()

        for cycle in range(1, 8):
            print(f"--- Cycle {cycle} ---")

            # 1. Select rules (what would go in the prompt)
            selected_seeds = select_gauntlet_rules(buildlog_dir, seeds, select_k=5)
            selected_rules = selected_seeds["security_karen"].rules
            # Get IDs of selected rules
            selected_ids_set = set()
            for r in selected_rules:
                for i, orig in enumerate(sf.rules):
                    if orig.rule == r.rule:
                        selected_ids_set.add(get_rule_id(orig, "security_karen", i))
                        break

            print(f"  Rules in prompt: {len(selected_rules)}/15")

            # How many of the cited rules made it into selection?
            cited_in_selection = selected_ids_set & set(cited_ids)
            print(
                f"  Cited rules in selection: {len(cited_in_selection)}/3 {list(cited_in_selection)}"
            )

            # 2. Simulate review (cite the good rules)
            simulate_review(buildlog_dir, seeds, cited_ids)

            # 3. Show bandit state
            backend = get_learning_backend(buildlog_dir)
            stats = backend.get_stats(context=None)
            if stats:
                sorted_arms = sorted(
                    stats.items(), key=lambda x: x[1]["mean"], reverse=True
                )
                print("  Top 5 arms by posterior mean:")
                for arm_id, info in sorted_arms[:5]:
                    marker = " <-- CITED" if arm_id in cited_ids else ""
                    print(
                        f"    {arm_id}: mean={info['mean']:.3f}"
                        f" (a={info['alpha']:.1f}, b={info['beta']:.1f}){marker}"
                    )
            print()

        print("=" * 70)
        print("  RESULT: After 7 cycles, cited rules should dominate top-5")
        print("=" * 70)
        print()

        # Final selection with learning
        final_seeds = select_gauntlet_rules(buildlog_dir, seeds, select_k=5)
        final_rules = final_seeds["security_karen"].rules
        final_ids = set()
        for r in final_rules:
            for i, orig in enumerate(sf.rules):
                if orig.rule == r.rule:
                    final_ids.add(get_rule_id(orig, "security_karen", i))
                    break

        cited_in_final = final_ids & set(cited_ids)
        print(f"Final selection: {len(final_rules)} rules")
        print(f"Cited rules in final: {len(cited_in_final)}/3")
        print(
            f"Learning {'WORKS' if len(cited_in_final) == 3 else 'needs more cycles'}!"
        )


if __name__ == "__main__":
    main()
