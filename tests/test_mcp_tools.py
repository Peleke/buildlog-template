"""Tests for buildlog.mcp.tools module.

These tests verify the thin MCP wrappers correctly delegate to core operations.
"""

import json
from pathlib import Path

import pytest
import yaml

from buildlog.mcp.tools import (
    _ensure_message,
    _resolve_file_or_inline,
    _resolve_text_file_or_inline,
    buildlog_diff,
    buildlog_entry_list,
    buildlog_entry_new,
    buildlog_gauntlet_accept_risk,
    buildlog_gauntlet_generate,
    buildlog_gauntlet_issues,
    buildlog_gauntlet_rules,
    buildlog_import_seed,
    buildlog_learn_from_review,
    buildlog_overview,
    buildlog_promote,
    buildlog_reject,
    buildlog_status,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "buildlog"


class TestBuildlogStatus:
    """Tests for buildlog_status MCP tool."""

    def test_returns_dict(self):
        """Should return a dictionary (serializable for MCP)."""
        result = buildlog_status(buildlog_dir=str(FIXTURES_DIR))
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        """Should have all expected keys from StatusResult."""
        result = buildlog_status(buildlog_dir=str(FIXTURES_DIR))

        assert "skills" in result
        assert "total_entries" in result
        assert "total_skills" in result
        assert "by_confidence" in result
        assert "promotable_ids" in result
        assert "error" in result

    def test_returns_error_for_missing_dir(self, tmp_path):
        """Should return error field for missing directory."""
        result = buildlog_status(buildlog_dir=str(tmp_path / "nonexistent"))

        assert result["error"] is not None
        assert "No buildlog directory" in result["error"]

    def test_accepts_min_confidence(self):
        """Should accept min_confidence parameter."""
        low = buildlog_status(buildlog_dir=str(FIXTURES_DIR), min_confidence="low")
        high = buildlog_status(buildlog_dir=str(FIXTURES_DIR), min_confidence="high")

        # Both should work
        assert low["error"] is None
        assert high["error"] is None


class TestBuildlogPromote:
    """Tests for buildlog_promote MCP tool."""

    def test_returns_dict(self, tmp_path):
        """Should return a dictionary."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy fixture
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        # Get a skill ID
        status = buildlog_status(buildlog_dir=str(buildlog_dir))
        first_category = list(status["skills"].keys())[0]
        skill_id = status["skills"][first_category][0]["id"]

        result = buildlog_promote(
            skill_ids=[skill_id],
            target="claude_md",
            buildlog_dir=str(buildlog_dir),
        )

        assert isinstance(result, dict)

    def test_has_expected_keys(self, tmp_path):
        """Should have all expected keys from PromoteResult."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = buildlog_promote(
            skill_ids=["fake-id"],
            buildlog_dir=str(buildlog_dir),
        )

        assert "promoted_ids" in result
        assert "target" in result
        assert "rules_added" in result
        assert "not_found_ids" in result
        assert "message" in result
        assert "error" in result

    def test_accepts_target_parameter(self, tmp_path):
        """Should accept target parameter."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy fixture
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        # Get a skill ID
        status = buildlog_status(buildlog_dir=str(buildlog_dir))
        first_category = list(status["skills"].keys())[0]
        skill_id = status["skills"][first_category][0]["id"]

        result = buildlog_promote(
            skill_ids=[skill_id],
            target="settings_json",
            buildlog_dir=str(buildlog_dir),
        )

        assert result["target"] == "settings_json"

    def test_accepts_skill_target(self, tmp_path):
        """Should accept target='skill' for Anthropic Agent Skills format."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy fixture
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        # Get a skill ID
        status = buildlog_status(buildlog_dir=str(buildlog_dir))
        first_category = list(status["skills"].keys())[0]
        skill_id = status["skills"][first_category][0]["id"]

        result = buildlog_promote(
            skill_ids=[skill_id],
            target="skill",
            buildlog_dir=str(buildlog_dir),
        )

        assert result["target"] == "skill"
        assert result["error"] is None
        assert skill_id in result["promoted_ids"]

        # Verify SKILL.md was created
        skill_file = Path(".claude/skills/buildlog-learned/SKILL.md")
        assert skill_file.exists()
        content = skill_file.read_text()
        assert "---\n" in content  # YAML frontmatter
        assert "name: buildlog-learned" in content

        # Cleanup
        import shutil

        shutil.rmtree(".claude", ignore_errors=True)


class TestBuildlogReject:
    """Tests for buildlog_reject MCP tool."""

    def test_returns_dict(self, tmp_path):
        """Should return a dictionary."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = buildlog_reject(
            skill_ids=["arch-123"],
            buildlog_dir=str(buildlog_dir),
        )

        assert isinstance(result, dict)

    def test_has_expected_keys(self, tmp_path):
        """Should have all expected keys from RejectResult."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = buildlog_reject(
            skill_ids=["arch-123"],
            buildlog_dir=str(buildlog_dir),
        )

        assert "rejected_ids" in result
        assert "total_rejected" in result
        assert "error" in result

    def test_rejects_skill_ids(self, tmp_path):
        """Should reject provided skill IDs."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = buildlog_reject(
            skill_ids=["arch-123", "wf-456"],
            buildlog_dir=str(buildlog_dir),
        )

        assert "arch-123" in result["rejected_ids"]
        assert "wf-456" in result["rejected_ids"]
        assert result["total_rejected"] == 2


class TestBuildlogDiff:
    """Tests for buildlog_diff MCP tool."""

    def test_returns_dict(self, tmp_path):
        """Should return a dictionary."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy fixture
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        result = buildlog_diff(buildlog_dir=str(buildlog_dir))

        assert isinstance(result, dict)

    def test_has_expected_keys(self, tmp_path):
        """Should have all expected keys from DiffResult."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy fixture
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        result = buildlog_diff(buildlog_dir=str(buildlog_dir))

        assert "pending" in result
        assert "total_pending" in result
        assert "already_promoted" in result
        assert "already_rejected" in result
        assert "error" in result

    def test_returns_pending_skills(self, tmp_path):
        """Should return skills pending review."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy fixture
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        result = buildlog_diff(buildlog_dir=str(buildlog_dir))

        assert result["total_pending"] > 0
        assert result["already_promoted"] == 0
        assert result["already_rejected"] == 0


class TestBuildlogLearnFromReview:
    """Tests for buildlog_learn_from_review MCP tool."""

    def test_returns_dict(self, tmp_path):
        """Should return a dictionary."""
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

        result = buildlog_learn_from_review(
            issues=issues,
            source="test",
            buildlog_dir=str(buildlog_dir),
        )

        assert isinstance(result, dict)

    def test_has_expected_keys(self, tmp_path):
        """Should have all expected keys from LearnFromReviewResult."""
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

        result = buildlog_learn_from_review(
            issues=issues,
            buildlog_dir=str(buildlog_dir),
        )

        assert "new_learnings" in result
        assert "reinforced_learnings" in result
        assert "total_issues_processed" in result
        assert "source" in result
        assert "message" in result
        assert "error" in result

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
                "rule_learned": "Write tests first",
            },
        ]

        result = buildlog_learn_from_review(
            issues=issues,
            source="PR#42",
            buildlog_dir=str(buildlog_dir),
        )

        assert result["error"] is None
        assert len(result["new_learnings"]) == 2
        assert result["total_issues_processed"] == 2

    def test_reinforces_existing_learnings(self, tmp_path):
        """Should reinforce when same rule seen again."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        issues = [
            {
                "severity": "critical",
                "category": "architectural",
                "description": "Test",
                "rule_learned": "Same rule",
            }
        ]

        # First call
        result1 = buildlog_learn_from_review(
            issues=issues,
            source="PR#1",
            buildlog_dir=str(buildlog_dir),
        )
        assert len(result1["new_learnings"]) == 1

        # Second call with same rule
        result2 = buildlog_learn_from_review(
            issues=issues,
            source="PR#2",
            buildlog_dir=str(buildlog_dir),
        )
        assert len(result2["reinforced_learnings"]) == 1
        assert len(result2["new_learnings"]) == 0

    def test_returns_error_for_empty_issues(self, tmp_path):
        """Should return error when no issues provided."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = buildlog_learn_from_review(
            issues=[],
            buildlog_dir=str(buildlog_dir),
        )

        assert result["error"] is not None
        assert "No issues provided" in result["error"]


# =============================================================================
# New MCP Tool Tests (v0.10.0)
# =============================================================================


class TestBuildlogGauntletRules:
    """Tests for buildlog_gauntlet_rules MCP tool."""

    def test_returns_dict(self):
        """Should return a serializable dict."""
        result = buildlog_gauntlet_rules()
        assert isinstance(result, dict)
        assert "formatted" in result
        assert "total_rules" in result

    def test_filters_persona(self):
        """persona param should filter results."""
        result = buildlog_gauntlet_rules(persona="security_karen")
        if result["error"] is None:
            assert result["personas"] == ["security_karen"]

    def test_error_handling(self):
        """Invalid persona should set error key."""
        result = buildlog_gauntlet_rules(persona="nonexistent")
        assert result["error"] is not None


class TestBuildlogOverview:
    """Tests for buildlog_overview MCP tool."""

    def test_returns_dict(self):
        """Should return a dict with expected keys."""
        result = buildlog_overview(buildlog_dir=str(FIXTURES_DIR))
        assert isinstance(result, dict)
        assert "entries" in result
        assert "skills" in result
        assert "active_session" in result

    def test_empty_project(self, tmp_path):
        """Should work with fresh buildlog dir."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        result = buildlog_overview(buildlog_dir=str(buildlog_dir))
        assert result["entries"] == 0


class TestBuildlogEntryNew:
    """Tests for buildlog_entry_new MCP tool."""

    def _setup(self, tmp_path):
        bd = tmp_path / "buildlog"
        bd.mkdir()
        (bd / ".buildlog").mkdir()
        (bd / "_TEMPLATE.md").write_text("# [YYYY-MM-DD]\n")
        return bd

    def test_creates_file(self, tmp_path):
        """File should exist after call."""
        bd = self._setup(tmp_path)
        result = buildlog_entry_new(slug="test", buildlog_dir=str(bd))
        assert result["error"] is None
        assert Path(result["entry_path"]).exists()

    def test_returns_path(self, tmp_path):
        """Dict should have entry_path key."""
        bd = self._setup(tmp_path)
        result = buildlog_entry_new(slug="test", buildlog_dir=str(bd))
        assert "entry_path" in result

    def test_duplicate_error(self, tmp_path):
        """Error key should be set on duplicate."""
        bd = self._setup(tmp_path)
        buildlog_entry_new(slug="dup", entry_date="2026-01-01", buildlog_dir=str(bd))
        result = buildlog_entry_new(
            slug="dup", entry_date="2026-01-01", buildlog_dir=str(bd)
        )
        assert result["error"] is not None


class TestBuildlogEntryList:
    """Tests for buildlog_entry_list MCP tool."""

    def test_returns_entries(self, tmp_path):
        """Should return list of dicts with name, title."""
        bd = tmp_path / "buildlog"
        bd.mkdir()
        (bd / "2026-01-01-test.md").write_text("# Test Entry\n")

        result = buildlog_entry_list(buildlog_dir=str(bd))
        assert result["count"] == 1
        assert result["entries"][0]["name"] == "2026-01-01-test.md"
        assert result["entries"][0]["title"] == "Test Entry"

    def test_empty(self, tmp_path):
        """Should return empty list and count=0."""
        bd = tmp_path / "buildlog"
        bd.mkdir()

        result = buildlog_entry_list(buildlog_dir=str(bd))
        assert result["count"] == 0
        assert result["entries"] == []


# =============================================================================
# File-based parameter resolution tests (v0.11.1)
# =============================================================================


class TestResolveFileOrInline:
    """Tests for _resolve_file_or_inline helper."""

    def test_returns_inline(self):
        """Should return inline value when provided."""
        data = [{"a": 1}]
        assert _resolve_file_or_inline(data, None, "issues") == data

    def test_reads_json_file(self, tmp_path):
        """Should read and parse JSON file."""
        f = tmp_path / "data.json"
        f.write_text(json.dumps([{"severity": "critical"}]))
        result = _resolve_file_or_inline(None, str(f), "issues")
        assert result == [{"severity": "critical"}]

    def test_raises_on_both(self):
        """Should raise ValueError when both inline and file provided."""
        with pytest.raises(ValueError, match="not both"):
            _resolve_file_or_inline([{"a": 1}], "/tmp/f.json", "issues")

    def test_raises_on_neither(self):
        """Should raise ValueError when neither provided."""
        with pytest.raises(ValueError, match="Provide either"):
            _resolve_file_or_inline(None, None, "issues")

    def test_raises_on_missing_file(self, tmp_path):
        """Should raise FileNotFoundError for nonexistent file."""
        with pytest.raises(FileNotFoundError, match="File not found"):
            _resolve_file_or_inline(None, str(tmp_path / "nope.json"), "issues")

    def test_raises_on_non_array_json(self, tmp_path):
        """Should raise ValueError if JSON is not an array."""
        f = tmp_path / "obj.json"
        f.write_text(json.dumps({"not": "an array"}))
        with pytest.raises(ValueError, match="Expected JSON array"):
            _resolve_file_or_inline(None, str(f), "issues")

    def test_raises_on_malformed_json(self, tmp_path):
        """Should raise ValueError on malformed JSON (subclass)."""
        f = tmp_path / "bad.json"
        f.write_text("{not valid json")
        with pytest.raises(ValueError):
            _resolve_file_or_inline(None, str(f), "issues")


class TestResolveTextFileOrInline:
    """Tests for _resolve_text_file_or_inline helper."""

    def test_returns_inline(self):
        """Should return inline string when provided."""
        assert _resolve_text_file_or_inline("hello", None, "source_text") == "hello"

    def test_reads_text_file(self, tmp_path):
        """Should read text file contents."""
        f = tmp_path / "source.txt"
        f.write_text("some content here")
        assert (
            _resolve_text_file_or_inline(None, str(f), "source_text")
            == "some content here"
        )

    def test_raises_on_both(self):
        """Should raise ValueError when both provided."""
        with pytest.raises(ValueError, match="not both"):
            _resolve_text_file_or_inline("hi", "/tmp/f.txt", "source_text")

    def test_raises_on_neither(self):
        """Should raise ValueError when neither provided."""
        with pytest.raises(ValueError, match="Provide either"):
            _resolve_text_file_or_inline(None, None, "source_text")


class TestFileBasedGauntletIssues:
    """Integration tests for buildlog_gauntlet_issues with file param."""

    def test_file_works(self, tmp_path):
        """Should accept issues via file path."""
        bd = tmp_path / "buildlog"
        bd.mkdir()

        issues = [
            {
                "severity": "minor",
                "category": "testing",
                "description": "Test issue",
                "rule_learned": "Test rule",
            }
        ]
        f = tmp_path / "issues.json"
        f.write_text(json.dumps(issues))

        result = buildlog_gauntlet_issues(
            issues_file=str(f),
            buildlog_dir=str(bd),
        )
        assert "error" not in result or result.get("error") is None
        assert result["action"] in (
            "fix_criticals",
            "checkpoint_majors",
            "checkpoint_minors",
            "clean",
        )

    def test_mutual_exclusion_error(self, tmp_path):
        """Should return error when both inline and file provided."""
        result = buildlog_gauntlet_issues(
            issues=[{"severity": "minor"}],
            issues_file="/tmp/x.json",
            buildlog_dir=str(tmp_path),
        )
        assert result["error"] is not None
        assert "not both" in result["error"]

    def test_neither_error(self):
        """Should return error when neither provided."""
        result = buildlog_gauntlet_issues(buildlog_dir="buildlog")
        assert result["error"] is not None
        assert "Provide either" in result["error"]


class TestFileBasedLearnFromReview:
    """Integration tests for buildlog_learn_from_review with file param."""

    def test_file_works(self, tmp_path):
        """Should accept issues via file path."""
        bd = tmp_path / "buildlog"
        bd.mkdir()

        issues = [
            {
                "severity": "major",
                "category": "architectural",
                "description": "No validation",
                "rule_learned": "Validate inputs",
            }
        ]
        f = tmp_path / "issues.json"
        f.write_text(json.dumps(issues))

        result = buildlog_learn_from_review(
            issues_file=str(f),
            source="test",
            buildlog_dir=str(bd),
        )
        assert result["error"] is None
        assert result["total_issues_processed"] == 1


class TestFileBasedGauntletAcceptRisk:
    """Integration tests for buildlog_gauntlet_accept_risk with file param."""

    def test_file_works(self, tmp_path):
        """Should accept remaining_issues via file path."""
        issues = [
            {
                "severity": "minor",
                "category": "testing",
                "description": "Missing edge case test",
            }
        ]
        f = tmp_path / "remaining.json"
        f.write_text(json.dumps(issues))

        result = buildlog_gauntlet_accept_risk(issues_file=str(f))
        assert result["accepted_issues"] == 1

    def test_neither_error(self):
        """Should return error when neither provided."""
        result = buildlog_gauntlet_accept_risk()
        assert result["error"] is not None
        assert "Provide either" in result["error"]


class TestFileBasedGauntletGenerate:
    """Integration tests for buildlog_gauntlet_generate with file param."""

    def test_mutual_exclusion_error(self, tmp_path):
        """Should return error when both inline and file provided."""
        f = tmp_path / "src.txt"
        f.write_text("some text")

        result = buildlog_gauntlet_generate(
            source_text="inline text",
            source_file=str(f),
            persona="test",
        )
        assert result["error"] is not None
        assert "not both" in result["error"]

    def test_neither_error(self):
        """Should return error when neither provided."""
        result = buildlog_gauntlet_generate(persona="test")
        assert result["error"] is not None
        assert "Provide either" in result["error"]


class TestBuildlogImportSeed:
    """Tests for buildlog_import_seed MCP tool."""

    def test_happy_path(self, tmp_path, monkeypatch):
        """Should import valid seed file and return result dict."""
        monkeypatch.chdir(tmp_path)
        source = tmp_path / "test.yaml"
        source.write_text(
            yaml.dump(
                {
                    "persona": "test_persona",
                    "version": 1,
                    "rules": [{"rule": "Always test", "category": "testing"}],
                }
            )
        )
        target_dir = tmp_path / "seeds"

        result = buildlog_import_seed(
            source=str(source),
            target_dir=str(target_dir),
            buildlog_dir=str(tmp_path / "buildlog"),
        )

        assert "error" not in result
        assert result["persona"] == "test_persona"
        assert result["rule_count"] == 1
        assert (target_dir / "test.yaml").exists()

    def test_error_on_missing_source(self, tmp_path, monkeypatch):
        """Should return error dict for missing source file."""
        monkeypatch.chdir(tmp_path)
        result = buildlog_import_seed(
            source=str(tmp_path / "nonexistent.yaml"),
            target_dir=str(tmp_path / "seeds"),
        )

        assert result["error"] is not None
        assert "not found" in result["error"]
        assert result["rule_count"] == 0

    def test_error_on_invalid_yaml(self, tmp_path, monkeypatch):
        """Should return error dict for invalid seed file."""
        monkeypatch.chdir(tmp_path)
        source = tmp_path / "bad.yaml"
        source.write_text("- just\n- a\n- list")

        result = buildlog_import_seed(
            source=str(source),
            target_dir=str(tmp_path / "seeds"),
        )

        assert result["error"] is not None
        assert "Invalid" in result["error"]

    def test_rejects_path_traversal(self, tmp_path, monkeypatch):
        """Should reject target_dir outside working directory."""
        monkeypatch.chdir(tmp_path)
        source = tmp_path / "test.yaml"
        source.write_text(
            yaml.dump(
                {
                    "persona": "test",
                    "version": 1,
                    "rules": [{"rule": "Test"}],
                }
            )
        )

        result = buildlog_import_seed(
            source=str(source),
            target_dir="/tmp/evil_outside_cwd",
        )

        assert result["error"] is not None
        assert "within working directory" in result["error"]


# ---------------------------------------------------------------------------
# _ensure_message tests
# ---------------------------------------------------------------------------


class TestEnsureMessage:
    """Tests for _ensure_message() MCP helper."""

    def test_message_present_unchanged(self):
        """When message is already set, return as-is."""
        d = {"message": "hello", "error": None}
        result = _ensure_message(d)
        assert result["message"] == "hello"

    def test_empty_message_falls_back_to_error(self):
        """Empty message + error present → message = error."""
        d = {"message": "", "error": "something broke"}
        result = _ensure_message(d)
        assert result["message"] == "something broke"

    def test_missing_message_falls_back_to_error(self):
        """No message key + error present → message = error."""
        d = {"error": "not found"}
        result = _ensure_message(d)
        assert result["message"] == "not found"

    def test_none_message_falls_back_to_error(self):
        """message=None + error present → message = error."""
        d = {"message": None, "error": "null case"}
        result = _ensure_message(d)
        assert result["message"] == "null case"

    def test_both_empty_no_crash(self):
        """Both message and error empty → no change."""
        d = {"message": "", "error": ""}
        result = _ensure_message(d)
        assert result["message"] == ""

    def test_neither_present_no_crash(self):
        """No message, no error → no crash, no message added."""
        d = {"data": 42}
        result = _ensure_message(d)
        assert "message" not in result

    def test_does_not_mutate_input(self):
        """Must not mutate the input dict when fallback is applied."""
        d = {"message": "", "error": "fallback"}
        result = _ensure_message(d)
        assert result["message"] == "fallback"
        assert d["message"] == ""  # original unchanged

    def test_no_copy_when_message_present(self):
        """When no fallback needed, may return same object (no copy needed)."""
        d = {"message": "ok", "error": None}
        result = _ensure_message(d)
        assert result is d  # no copy overhead

    def test_mcp_tools_have_message_in_response(self):
        """Status tool (representative) should include message in output."""
        result = buildlog_status(buildlog_dir=str(FIXTURES_DIR))
        assert "message" in result
        assert isinstance(result["message"], str)

    def test_error_path_has_message_via_fallback(self, tmp_path):
        """Error path should get message populated via _ensure_message."""
        result = buildlog_status(buildlog_dir=str(tmp_path / "nope"))
        assert result["error"] is not None
        assert result["message"]  # non-empty
