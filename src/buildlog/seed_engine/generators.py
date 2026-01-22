"""Seed file generators for Step 4 of the seed engine pipeline.

Generators take categorized rules and produce the final seed file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from buildlog.seed_engine.models import CategorizedRule


@dataclass
class SeedGenerator:
    """Generate YAML seed files from categorized rules.

    Usage:
        generator = SeedGenerator(
            persona="test_terrorist",
            version=1,
            output_dir=Path(".buildlog/seeds"),
        )

        seed_file = generator.generate(categorized_rules)
        generator.write(seed_file)
    """

    persona: str
    version: int = 1
    output_dir: Path | None = None
    header_comment: str | None = None

    def generate(self, rules: list[CategorizedRule]) -> dict[str, Any]:
        """Generate seed file dictionary from categorized rules.

        Args:
            rules: The categorized rules to include.

        Returns:
            Seed file as dictionary (ready for YAML serialization).
        """
        # Validate all rules are complete
        incomplete = [r for r in rules if not self._is_complete(r)]
        if incomplete:
            raise ValueError(
                f"{len(incomplete)} rules are incomplete. "
                f"First: '{incomplete[0].rule[:50]}...'"
            )

        return {
            "persona": self.persona,
            "version": self.version,
            "rules": [r.to_seed_dict() for r in rules],
        }

    def write(
        self,
        seed_data: dict[str, Any],
        path: Path | None = None,
    ) -> Path:
        """Write seed file to disk.

        Args:
            seed_data: The seed file dictionary.
            path: Output path. If None, uses output_dir/persona.yaml.

        Returns:
            Path to written file.
        """
        if path is None:
            if self.output_dir is None:
                raise ValueError("No output path or output_dir specified")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"{self.persona}.yaml"

        # Build YAML content with optional header
        yaml_content = yaml.dump(
            seed_data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )

        # Add header comment if provided
        if self.header_comment:
            lines = [f"# {line}" for line in self.header_comment.split("\n")]
            header = "\n".join(lines) + "\n\n"
            yaml_content = header + yaml_content

        path.write_text(yaml_content)
        return path

    def _is_complete(self, rule: CategorizedRule) -> bool:
        """Check if a rule has all required fields."""
        return bool(
            rule.rule.strip()
            and rule.context.strip()
            and rule.antipattern.strip()
            and rule.rationale.strip()
            and rule.category.strip()
        )

    def validate(self, seed_data: dict[str, Any]) -> list[str]:
        """Validate seed file structure.

        Args:
            seed_data: The seed file dictionary.

        Returns:
            List of validation issues (empty if valid).
        """
        issues = []

        if "persona" not in seed_data:
            issues.append("Missing 'persona' field")
        if "version" not in seed_data:
            issues.append("Missing 'version' field")
        if "rules" not in seed_data:
            issues.append("Missing 'rules' field")
            return issues

        for i, rule in enumerate(seed_data.get("rules", [])):
            prefix = f"Rule {i + 1}"
            if not rule.get("rule"):
                issues.append(f"{prefix}: Missing 'rule' text")
            if not rule.get("context"):
                issues.append(
                    f"{prefix}: Missing 'context' (required for defensibility)"
                )
            if not rule.get("antipattern"):
                issues.append(
                    f"{prefix}: Missing 'antipattern' (required for defensibility)"
                )
            if not rule.get("rationale"):
                issues.append(
                    f"{prefix}: Missing 'rationale' (required for defensibility)"
                )

        return issues
