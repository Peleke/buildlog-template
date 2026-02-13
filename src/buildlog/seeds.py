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
    "ImportSeedResult",
    "load_seed_file",
    "load_all_seeds",
    "seeds_to_skills",
    "import_seed_file",
    "get_package_seeds_dir",
    "get_default_seeds_dir",
    "get_rule_id",
    "build_rule_id_index",
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
    provenance: dict[str, Any] | None = None


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
            raw_prov = rule_data.get("provenance")
            provenance = raw_prov if isinstance(raw_prov, dict) else None
            rules.append(
                SeedRule(
                    rule=rule_data["rule"],
                    category=rule_data.get("category", "general"),
                    context=rule_data.get("context", ""),
                    antipattern=rule_data.get("antipattern", ""),
                    rationale=rule_data.get("rationale", ""),
                    tags=rule_data.get("tags", []),
                    references=refs,
                    provenance=provenance,
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
        # provenance must be a dict if present
        prov = rule.get("provenance")
        if prov is not None and not isinstance(prov, dict):
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
            provenance=seed.provenance,
        )
        skills.append(skill)

    return skills


@dataclass
class ImportSeedResult:
    """Result of importing a seed file."""

    persona: str
    rule_count: int
    provenance_count: int
    target_path: str
    version_changed: bool
    decayed_rules: int
    message: str


def _check_version_decay(
    old_file: SeedFile,
    new_file: SeedFile,
    buildlog_dir: Path,
) -> tuple[bool, int]:
    """Compare graph_version between old and new seed files per rule.

    For rules whose provenance.graph_version has changed, decay the
    corresponding bandit arm to reduce stale learned signal.

    Args:
        old_file: Previously imported seed file.
        new_file: Newly imported seed file.
        buildlog_dir: Path to buildlog directory (for bandit state).

    Returns:
        Tuple of (version_changed, decayed_count).
    """
    from buildlog.core.learning import get_learning_backend

    # Build lookup: rule text → provenance for old and new
    def _version_map(sf: SeedFile) -> dict[str, str | None]:
        result: dict[str, str | None] = {}
        for rule in sf.rules:
            version = None
            if rule.provenance and "graph_version" in rule.provenance:
                version = str(rule.provenance["graph_version"])
            result[rule.rule] = version
        return result

    old_versions = _version_map(old_file)
    new_versions = _version_map(new_file)

    changed_rules: list[str] = []
    for rule_text, new_ver in new_versions.items():
        old_ver = old_versions.get(rule_text)
        if old_ver is not None and new_ver is not None and old_ver != new_ver:
            changed_rules.append(rule_text)

    if not changed_rules:
        return False, 0

    # Decay bandit arms for changed rules
    bandit = get_learning_backend(buildlog_dir)
    decayed = 0
    for rule_text in changed_rules:
        # Find the category to generate the skill ID
        for rule in new_file.rules:
            if rule.rule == rule_text:
                skill_id = _generate_skill_id(rule.category, rule_text)
                if bandit.decay_arm(skill_id):
                    decayed += 1
                break

    return True, decayed


def import_seed_file(
    source_path: Path,
    target_dir: Path | None = None,
    buildlog_dir: Path | None = None,
) -> ImportSeedResult:
    """Import a seed file, optionally detecting version changes and decaying bandit arms.

    Args:
        source_path: Path to the source YAML seed file.
        target_dir: Directory to copy the seed file into. Defaults to
            .buildlog/seeds/ in the current directory.
        buildlog_dir: Path to buildlog directory for bandit state.
            Defaults to ./buildlog.

    Returns:
        ImportSeedResult with import summary.

    Raises:
        FileNotFoundError: If source_path doesn't exist.
        ValueError: If the source file is invalid.
    """
    import shutil

    if not source_path.exists():
        raise FileNotFoundError(f"Seed file not found: {source_path}")

    # Load and validate source
    new_file = load_seed_file(source_path)
    if new_file is None:
        raise ValueError(f"Invalid seed file: {source_path}")

    # Resolve defaults
    if target_dir is None:
        target_dir = Path(".buildlog") / "seeds"
    if buildlog_dir is None:
        buildlog_dir = Path("buildlog")

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / source_path.name

    # Check for version changes if target already exists
    version_changed = False
    decayed_rules = 0
    if target_path.exists():
        old_file = load_seed_file(target_path)
        if old_file is not None:
            version_changed, decayed_rules = _check_version_decay(
                old_file, new_file, buildlog_dir
            )

    # Copy source to target
    shutil.copy2(source_path, target_path)

    # Count rules with provenance
    provenance_count = sum(1 for r in new_file.rules if r.provenance is not None)

    parts = [f"Imported {len(new_file.rules)} rules for {new_file.persona}"]
    if provenance_count > 0:
        parts.append(f"{provenance_count} with provenance")
    if version_changed:
        parts.append(f"version changed, {decayed_rules} arms decayed")

    return ImportSeedResult(
        persona=new_file.persona,
        rule_count=len(new_file.rules),
        provenance_count=provenance_count,
        target_path=str(target_path),
        version_changed=version_changed,
        decayed_rules=decayed_rules,
        message=" | ".join(parts),
    )


def get_rules_for_persona(all_skills: list[Skill], persona: str) -> list[Skill]:
    """Filter skills to those relevant for a specific persona.

    Args:
        all_skills: All available skills (seeded + learned).
        persona: The persona to filter for.

    Returns:
        Skills tagged for this persona.
    """
    return [s for s in all_skills if persona in s.persona_tags]


def get_rule_id(seed_rule: SeedRule, persona: str, index: int) -> str:
    """Get a stable, citable ID for a seed rule.

    Uses ``provenance["id"]`` if present, otherwise falls back to
    ``{persona}:rule:{index}`` which is deterministic as long as
    the seed file doesn't reorder rules.

    Args:
        seed_rule: The seed rule to get an ID for.
        persona: The persona this rule belongs to.
        index: The rule's position in the seed file (0-based).

    Returns:
        A string rule ID suitable for citation in gauntlet prompts.
    """
    if seed_rule.provenance and isinstance(seed_rule.provenance.get("id"), str):
        return seed_rule.provenance["id"]
    return f"{persona}:rule:{index}"


def build_rule_id_index(
    seeds: dict[str, SeedFile],
) -> dict[str, dict[str, Any]]:
    """Build a flat index mapping every rule ID to its metadata.

    Args:
        seeds: Dict mapping persona name to SeedFile (from ``load_all_seeds``).

    Returns:
        Dict mapping rule ID → ``{persona, rule_text, category, index}``.
    """
    index: dict[str, dict[str, Any]] = {}
    for persona_name, sf in seeds.items():
        for i, rule in enumerate(sf.rules):
            rule_id = get_rule_id(rule, persona_name, i)
            index[rule_id] = {
                "persona": persona_name,
                "rule_text": rule.rule,
                "category": rule.category,
                "index": i,
            }
    return index
