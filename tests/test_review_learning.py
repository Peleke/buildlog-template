"""Tests for review learning functionality."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from buildlog.core.operations import (
    LearnFromReviewResult,
    ReviewIssue,
    ReviewLearning,
    learn_from_review,
)
from buildlog.skills import generate_skills


class TestReviewIssue:
    """Tests for ReviewIssue dataclass."""

    def test_from_dict_with_all_fields(self):
        """Should create ReviewIssue from complete dict."""
        data = {
            "severity": "critical",
            "category": "architectural",
            "description": "Score bounds not validated",
            "rule_learned": "Validate invariants at function boundaries",
            "location": "src/buildlog/confidence.py:233",
            "why_it_matters": "Allows invalid state to propagate",
            "functional_principle": "Parse, don't validate",
        }
        issue = ReviewIssue.from_dict(data)

        assert issue.severity == "critical"
        assert issue.category == "architectural"
        assert issue.description == "Score bounds not validated"
        assert issue.rule_learned == "Validate invariants at function boundaries"
        assert issue.location == "src/buildlog/confidence.py:233"
        assert issue.why_it_matters == "Allows invalid state to propagate"
        assert issue.functional_principle == "Parse, don't validate"

    def test_from_dict_with_minimal_fields(self):
        """Should create ReviewIssue with defaults for missing optional fields."""
        data = {
            "severity": "major",
            "category": "workflow",
            "description": "Missing docstring",
            "rule_learned": "Document public functions",
        }
        issue = ReviewIssue.from_dict(data)

        assert issue.severity == "major"
        assert issue.category == "workflow"
        assert issue.location is None
        assert issue.why_it_matters is None
        assert issue.functional_principle is None

    def test_from_dict_with_empty_dict(self):
        """Should handle empty dict with sensible defaults."""
        issue = ReviewIssue.from_dict({})

        assert issue.severity == "minor"
        assert issue.category == "workflow"
        assert issue.description == ""
        assert issue.rule_learned == ""


class TestReviewLearning:
    """Tests for ReviewLearning dataclass."""

    def test_to_dict_and_from_dict_roundtrip(self):
        """Should serialize and deserialize correctly."""
        now = datetime.now(timezone.utc)
        learning = ReviewLearning(
            id="arch-abc123",
            rule="Validate at boundaries",
            category="architectural",
            severity="critical",
            source="review:PR#13",
            first_seen=now,
            last_reinforced=now,
            reinforcement_count=3,
            contradiction_count=1,
            functional_principle="Parse, don't validate",
        )

        serialized = learning.to_dict()
        restored = ReviewLearning.from_dict(serialized)

        assert restored.id == learning.id
        assert restored.rule == learning.rule
        assert restored.category == learning.category
        assert restored.severity == learning.severity
        assert restored.source == learning.source
        assert restored.reinforcement_count == learning.reinforcement_count
        assert restored.contradiction_count == learning.contradiction_count
        assert restored.functional_principle == learning.functional_principle

    def test_to_confidence_metrics(self):
        """Should convert to ConfidenceMetrics correctly."""
        now = datetime.now(timezone.utc)
        learning = ReviewLearning(
            id="wf-xyz789",
            rule="Test before commit",
            category="workflow",
            severity="major",
            source="review:2024-01-15",
            first_seen=now,
            last_reinforced=now,
            reinforcement_count=5,
            contradiction_count=2,
        )

        metrics = learning.to_confidence_metrics()

        assert metrics.reinforcement_count == 5
        assert metrics.contradiction_count == 2
        assert metrics.first_seen == now
        assert metrics.last_reinforced == now


class TestLearnFromReview:
    """Tests for learn_from_review() operation."""

    def test_creates_new_learnings(self, tmp_path):
        """Should create new learnings from issues."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        issues = [
            {
                "severity": "critical",
                "category": "architectural",
                "description": "No bounds check",
                "rule_learned": "Validate at boundaries",
            },
            {
                "severity": "major",
                "category": "workflow",
                "description": "Missing tests",
                "rule_learned": "Write tests for new features",
            },
        ]

        result = learn_from_review(buildlog_dir, issues, source="PR#42")

        assert result.error is None
        assert len(result.new_learnings) == 2
        assert len(result.reinforced_learnings) == 0
        assert result.total_issues_processed == 2
        assert "PR#42" in result.source

    def test_persists_to_file(self, tmp_path):
        """Should persist learnings to review_learnings.json."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        issues = [
            {
                "severity": "critical",
                "category": "architectural",
                "description": "Test issue",
                "rule_learned": "Test rule",
            }
        ]

        learn_from_review(buildlog_dir, issues, source="test")

        learnings_file = buildlog_dir / ".buildlog" / "review_learnings.json"
        assert learnings_file.exists()

        data = json.loads(learnings_file.read_text())
        assert "learnings" in data
        assert "review_history" in data
        assert len(data["learnings"]) == 1
        assert len(data["review_history"]) == 1

    def test_reinforces_existing_learnings(self, tmp_path):
        """Should reinforce existing learning when same rule seen again."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        issues = [
            {
                "severity": "critical",
                "category": "architectural",
                "description": "No bounds check",
                "rule_learned": "Validate at boundaries",
            }
        ]

        # First call - creates new
        result1 = learn_from_review(buildlog_dir, issues, source="PR#1")
        assert len(result1.new_learnings) == 1
        assert len(result1.reinforced_learnings) == 0

        # Second call with same rule - reinforces
        result2 = learn_from_review(buildlog_dir, issues, source="PR#2")
        assert len(result2.new_learnings) == 0
        assert len(result2.reinforced_learnings) == 1

        # Check reinforcement count increased
        learnings_file = buildlog_dir / ".buildlog" / "review_learnings.json"
        data = json.loads(learnings_file.read_text())
        learning_id = result1.new_learnings[0]
        assert data["learnings"][learning_id]["reinforcement_count"] == 2

    def test_skips_issues_without_rule_learned(self, tmp_path):
        """Should skip issues that don't have rule_learned."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        issues = [
            {
                "severity": "critical",
                "category": "architectural",
                "description": "Has a rule",
                "rule_learned": "This is a rule",
            },
            {
                "severity": "minor",
                "category": "workflow",
                "description": "No rule here",
                # Missing rule_learned
            },
            {
                "severity": "major",
                "category": "tool_usage",
                "description": "Empty rule",
                "rule_learned": "   ",  # Whitespace only
            },
        ]

        result = learn_from_review(buildlog_dir, issues, source="test")

        assert result.total_issues_processed == 1
        assert len(result.new_learnings) == 1

    def test_returns_error_for_empty_issues(self, tmp_path):
        """Should return error when no issues provided."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = learn_from_review(buildlog_dir, [], source="test")

        assert result.error is not None
        assert "No issues provided" in result.error
        assert result.total_issues_processed == 0

    def test_generates_deterministic_ids(self, tmp_path):
        """Same rule should always get same ID."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        issues = [
            {
                "severity": "critical",
                "category": "architectural",
                "description": "Test 1",
                "rule_learned": "  Validate at Boundaries  ",  # With whitespace
            }
        ]

        result1 = learn_from_review(buildlog_dir, issues, source="PR#1")

        # Same rule with different whitespace/case
        issues[0]["rule_learned"] = "validate at boundaries"
        result2 = learn_from_review(buildlog_dir, issues, source="PR#2")

        # Should have same ID (reinforced, not new)
        assert len(result2.reinforced_learnings) == 1
        assert result1.new_learnings[0] == result2.reinforced_learnings[0]

    def test_auto_generates_source_if_not_provided(self, tmp_path):
        """Should auto-generate source with timestamp if not provided."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        issues = [
            {
                "severity": "minor",
                "category": "workflow",
                "description": "Test",
                "rule_learned": "Test rule",
            }
        ]

        result = learn_from_review(buildlog_dir, issues)

        assert "review:" in result.source

    def test_records_review_history(self, tmp_path):
        """Should record each review in history."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        issues = [
            {
                "severity": "major",
                "category": "architectural",
                "description": "Test",
                "rule_learned": "Rule 1",
            }
        ]

        learn_from_review(buildlog_dir, issues, source="PR#1")
        learn_from_review(buildlog_dir, issues, source="PR#2")

        learnings_file = buildlog_dir / ".buildlog" / "review_learnings.json"
        data = json.loads(learnings_file.read_text())

        assert len(data["review_history"]) == 2
        assert data["review_history"][0]["source"] == "review:PR#1"
        assert data["review_history"][1]["source"] == "review:PR#2"


class TestGenerateSkillsWithReviewLearnings:
    """Tests for generate_skills() with review learnings integration."""

    def test_includes_review_learnings_by_default(self, tmp_path):
        """Should include review learnings when not explicitly disabled."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Create a buildlog entry
        entry = buildlog_dir / "2024-01-01-test.md"
        entry.write_text(
            """---
title: Test Entry
date: 2024-01-01
---

## Insights

### Architectural
- Test architectural pattern
"""
        )

        # Create a review learning
        issues = [
            {
                "severity": "critical",
                "category": "architectural",
                "description": "Review issue",
                "rule_learned": "Review learning rule",
            }
        ]
        learn_from_review(buildlog_dir, issues, source="test")

        # Generate skills
        skill_set = generate_skills(buildlog_dir, include_review_learnings=True)

        # Should have both the buildlog skill and review learning
        arch_skills = skill_set.skills.get("architectural", [])
        rules = [s.rule for s in arch_skills]
        assert "Review learning rule" in rules

    def test_excludes_review_learnings_when_disabled(self, tmp_path):
        """Should exclude review learnings when include_review_learnings=False."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Create a buildlog entry
        entry = buildlog_dir / "2024-01-01-test.md"
        entry.write_text(
            """---
title: Test Entry
date: 2024-01-01
---

## Insights

### Architectural
- Test architectural pattern
"""
        )

        # Create a review learning
        issues = [
            {
                "severity": "critical",
                "category": "architectural",
                "description": "Review issue",
                "rule_learned": "Review learning rule",
            }
        ]
        learn_from_review(buildlog_dir, issues, source="test")

        # Generate skills without review learnings
        skill_set = generate_skills(buildlog_dir, include_review_learnings=False)

        # Should NOT have the review learning
        arch_skills = skill_set.skills.get("architectural", [])
        rules = [s.rule for s in arch_skills]
        assert "Review learning rule" not in rules

    def test_handles_missing_learnings_file(self, tmp_path):
        """Should work fine when no review_learnings.json exists."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Create a buildlog entry
        entry = buildlog_dir / "2024-01-01-test.md"
        entry.write_text(
            """---
title: Test Entry
date: 2024-01-01
---

## Insights

### Workflow
- Test workflow pattern
"""
        )

        # Should not fail
        skill_set = generate_skills(buildlog_dir, include_review_learnings=True)

        assert skill_set is not None
