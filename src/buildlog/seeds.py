"""Load curated seed rules for reviewer personas.

Seed files provide defensible, human-curated rules that reviewers
can use immediately without requiring learned data. Each persona
(security_karen, test_terrorist, ruthless_reviewer) can have its
own seed file with domain-specific rules.

Seed files are YAML with the following format:

```yaml
persona: security_karen
version: 1
rules:
  - rule: "Parameterize all SQL queries"
    category: security
    context: "Any code constructing SQL from user input"
    antipattern: "String concatenation or f-strings with user data in SQL"
    rationale: "SQL injection is OWASP A03 - prevents data breach"
    tags: [sql, injection, owasp]
    references:
      - url: "https://owasp.org/Top10/A03_2021-Injection/"
        title: "OWASP A03:2021 Injection"
```
"""

from __future__ import annotations

__all__ = [
    "SeedRule",
    "SeedFile",
    "load_seed_file",
    "load_all_seeds",
    "seeds_to_skills",
    "get_package_seeds_dir",
    "get_default_seeds_dir",
]

import logging
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from buildlog.skills import Skill, _generate_skill_id

logger = logging.getLogger(__name__)


def get_package_seeds_dir() -> Path | None:
    """Get the path to bundled seed files in the package.

    Returns:
        Path to the package's data/seeds directory, or None if not found.
    """
    try:
        # Python 3.9+ way to get package resources
        with resources.as_file(resources.files("buildlog").joinpath("data/seeds")) as p:
            if p.exists():
                return p
    except (TypeError, FileNotFoundError):
        pass

    # Fallback: try relative to this file
    fallback = Path(__file__).parent / "data" / "seeds"
    if fallback.exists():
        return fallback

    return None


def get_default_seeds_dir() -> Path | None:
    """Get the default seeds directory, checking multiple locations.

    Priority:
    1. Local .buildlog/seeds/ (project-specific overrides)
    2. Local buildlog/.buildlog/seeds/ (buildlog template structure)
    3. Package bundled seeds (installed with pip)

    Returns:
        Path to the seeds directory with most precedence, or None if none found.
    """
    # Check local project seeds first (allows overrides)
    local_seeds = Path(".buildlog") / "seeds"
    if local_seeds.exists() and any(local_seeds.glob("*.yaml")):
        return local_seeds

    # Check buildlog template structure
    buildlog_seeds = Path("buildlog") / ".buildlog" / "seeds"
    if buildlog_seeds.exists() and any(buildlog_seeds.glob("*.yaml")):
        return buildlog_seeds

    # Fall back to package seeds
    return get_package_seeds_dir()


@dataclass
class SeedReference:
    """A reference/citation for a seed rule."""

    url: str
    title: str


@dataclass
class SeedRule:
    """A curated seed rule for a reviewer persona.

    Unlike learned Skills, seed rules come with full defensibility
    metadata from the start: context, antipattern, rationale, and
    references to authoritative sources.
    """

    rule: str
    category: str
    context: str
    antipattern: str
    rationale: str
    tags: list[str] = field(default_factory=list)
    references: list[SeedReference] = field(default_factory=list)


@dataclass
class SeedFile:
    """A collection of seed rules for a persona."""

    persona: str
    version: int
    rules: list[SeedRule]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SeedFile:
        """Parse a seed file from dictionary (loaded YAML)."""
        rules = []
        for rule_data in data.get("rules", []):
            refs = [
                SeedReference(url=r["url"], title=r["title"])
                for r in rule_data.get("references", [])
            ]
            rules.append(
                SeedRule(
                    rule=rule_data["rule"],
                    category=rule_data.get("category", "security"),
                    context=rule_data.get("context", ""),
                    antipattern=rule_data.get("antipattern", ""),
                    rationale=rule_data.get("rationale", ""),
                    tags=rule_data.get("tags", []),
                    references=refs,
                )
            )
        return cls(
            persona=data.get("persona", "unknown"),
            version=data.get("version", 1),
            rules=rules,
        )


def _validate_seed_schema(data: dict) -> bool:
    """Validate seed file has expected schema structure.

    Defense-in-depth validation for seed files. While yaml.safe_load
    prevents code execution, this ensures data structure matches expectations.

    Args:
        data: Parsed YAML data.

    Returns:
        True if schema is valid, False otherwise.
    """
    if not isinstance(data, dict):
        return False

    # Rules must be a list if present
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        return False

    # Each rule must be a dict with at least a "rule" key
    for rule in rules:
        if not isinstance(rule, dict):
            return False
        if "rule" not in rule:
            return False

    return True


def load_seed_file(path: Path) -> SeedFile | None:
    """Load a single seed file from disk.

    Args:
        path: Path to the YAML seed file.

    Returns:
        Parsed SeedFile or None if loading fails.

    Note:
        Uses yaml.safe_load which is safe from code execution attacks.
        Additional schema validation ensures data structure is as expected.
    """
    if not path.exists():
        logger.warning(f"Seed file not found: {path}")
        return None

    try:
        with open(path) as f:
            # yaml.safe_load is safe - no arbitrary code execution
            data = yaml.safe_load(f)

        # Validate schema before parsing
        if not _validate_seed_schema(data):
            logger.error(f"Invalid seed file schema: {path}")
            return None

        return SeedFile.from_dict(data)
    except (yaml.YAMLError, KeyError, TypeError) as e:
        logger.error(f"Failed to parse seed file {path}: {e}")
        return None


def load_all_seeds(seeds_dir: Path) -> dict[str, SeedFile]:
    """Load all seed files from a directory.

    Args:
        seeds_dir: Directory containing persona seed files.

    Returns:
        Dict mapping persona name to SeedFile.
    """
    result: dict[str, SeedFile] = {}

    if not seeds_dir.exists():
        logger.info(f"Seeds directory not found: {seeds_dir}")
        return result

    for seed_path in seeds_dir.glob("*.yaml"):
        seed_file = load_seed_file(seed_path)
        if seed_file:
            result[seed_file.persona] = seed_file
            logger.info(
                f"Loaded {len(seed_file.rules)} seed rules for {seed_file.persona}"
            )

    return result


def seeds_to_skills(seed_file: SeedFile) -> list[Skill]:
    """Convert seed rules to Skill objects.

    Seed rules become Skills with:
    - frequency=0 (not learned, seeded)
    - confidence="high" (curated by humans)
    - Full defensibility metadata

    Args:
        seed_file: The seed file to convert.

    Returns:
        List of Skill objects.
    """
    skills = []

    for seed in seed_file.rules:
        # Generate stable ID
        skill_id = _generate_skill_id(seed.category, seed.rule)

        # Build source references from citations
        sources = [f"seed:{seed_file.persona}:v{seed_file.version}"]
        sources.extend(ref.url for ref in seed.references)

        skill = Skill(
            id=skill_id,
            category=seed.category,
            rule=seed.rule,
            frequency=0,  # Seeded, not learned
            confidence="high",  # Human-curated
            sources=sources,
            tags=seed.tags,
            confidence_score=1.0,  # Full confidence in curated rules
            confidence_tier="entrenched",
            context=seed.context,
            antipattern=seed.antipattern,
            rationale=seed.rationale,
            persona_tags=[seed_file.persona],
        )
        skills.append(skill)

    return skills


def get_rules_for_persona(all_skills: list[Skill], persona: str) -> list[Skill]:
    """Filter skills to those relevant for a specific persona.

    Args:
        all_skills: All available skills (seeded + learned).
        persona: The persona to filter for.

    Returns:
        Skills tagged for this persona.
    """
    return [s for s in all_skills if persona in s.persona_tags]
