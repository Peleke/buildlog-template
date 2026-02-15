"""Exhaustive tests for gauntlet prompt and loop core ops and MCP tools."""

import json
from pathlib import Path

import pytest

from buildlog.core.operations import (
    GauntletLoopConfigResult,
    GauntletPromptResult,
    gauntlet_loop_config,
    generate_gauntlet_prompt,
)

# =============================================================================
# generate_gauntlet_prompt tests
# =============================================================================


class TestGenerateGauntletPrompt:
    """Tests for generate_gauntlet_prompt() core operation."""

    def test_returns_result_type(self):
        """Should return GauntletPromptResult."""
        result = generate_gauntlet_prompt("src/")
        assert isinstance(result, GauntletPromptResult)

    def test_returns_prompt_with_rules(self):
        """Prompt should contain review rules."""
        result = generate_gauntlet_prompt("src/")
        assert result.error is None
        assert result.prompt != ""
        assert "Review Gauntlet" in result.prompt

    def test_target_in_prompt(self):
        """Target path should appear in the prompt."""
        result = generate_gauntlet_prompt("src/api.py")
        assert "src/api.py" in result.prompt

    def test_includes_output_format(self):
        """Prompt should contain the expected issue output format."""
        result = generate_gauntlet_prompt("src/")
        assert '"severity"' in result.prompt
        assert '"rule_learned"' in result.prompt

    def test_includes_instructions(self):
        """Prompt should contain review instructions."""
        result = generate_gauntlet_prompt("src/")
        assert "Be ruthless" in result.prompt

    def test_filters_by_persona(self):
        """Should return only the specified persona's rules."""
        result = generate_gauntlet_prompt("src/", personas=["security_karen"])
        if result.error is None:
            assert result.personas == ["security_karen"]
            assert result.total_rules > 0

    def test_multiple_personas(self):
        """Should accept multiple persona names."""
        result = generate_gauntlet_prompt(
            "src/", personas=["security_karen", "test_terrorist"]
        )
        if result.error is None:
            assert len(result.personas) == 2

    def test_invalid_persona_returns_error(self):
        """Unknown persona should return error with available list."""
        result = generate_gauntlet_prompt("src/", personas=["nonexistent_persona"])
        assert result.error is not None
        assert "No matching personas" in result.error

    def test_none_personas_returns_all(self):
        """None personas should include all available."""
        result = generate_gauntlet_prompt("src/", personas=None)
        assert result.error is None
        assert len(result.personas) >= 2

    def test_total_rules_matches_persona_rules(self):
        """total_rules should equal sum of rules across personas."""
        result = generate_gauntlet_prompt("src/")
        assert result.total_rules > 0

    def test_message_describes_result(self):
        """Message should mention rule count and persona count."""
        result = generate_gauntlet_prompt("src/")
        if result.error is None:
            assert "rules" in result.message
            assert "personas" in result.message

    def test_persona_headers_in_prompt(self):
        """Each persona should have a named header section."""
        result = generate_gauntlet_prompt("src/")
        if result.error is None:
            for persona in result.personas:
                # Headers use title case with spaces
                header = persona.replace("_", " ").title()
                assert header in result.prompt

    def test_antipattern_included_when_present(self):
        """Rules with antipatterns should show them."""
        result = generate_gauntlet_prompt("src/")
        if result.error is None:
            # At least some rules should have antipatterns
            assert "Antipattern:" in result.prompt


# =============================================================================
# gauntlet_loop_config tests
# =============================================================================


class TestGauntletLoopConfig:
    """Tests for gauntlet_loop_config() core operation."""

    def test_returns_result_type(self):
        """Should return GauntletLoopConfigResult."""
        result = gauntlet_loop_config("src/")
        assert isinstance(result, GauntletLoopConfigResult)

    def test_all_fields_populated(self):
        """Should have all expected fields."""
        result = gauntlet_loop_config("src/")
        assert result.error is None
        assert result.target == "src/"
        assert len(result.personas) >= 2
        assert result.max_iterations == 10
        assert result.stop_at == "minors"
        assert result.auto_gh_issues is False
        assert isinstance(result.rules_by_persona, dict)
        assert isinstance(result.instructions, list)
        assert isinstance(result.issue_format, dict)
        assert result.prompt != ""

    def test_custom_max_iterations(self):
        """Should respect max_iterations parameter."""
        result = gauntlet_loop_config("src/", max_iterations=3)
        assert result.max_iterations == 3

    def test_custom_stop_at(self):
        """Should respect stop_at parameter."""
        result = gauntlet_loop_config("src/", stop_at="criticals")
        assert result.stop_at == "criticals"

    def test_auto_gh_issues_flag(self):
        """Should pass through auto_gh_issues."""
        result = gauntlet_loop_config("src/", auto_gh_issues=True)
        assert result.auto_gh_issues is True

    def test_filters_personas(self):
        """Should only include specified personas."""
        result = gauntlet_loop_config("src/", personas=["test_terrorist"])
        if result.error is None:
            assert result.personas == ["test_terrorist"]
            assert "test_terrorist" in result.rules_by_persona

    def test_invalid_persona_returns_error(self):
        """Unknown persona should return error."""
        result = gauntlet_loop_config("src/", personas=["nonexistent"])
        assert result.error is not None

    def test_rules_by_persona_has_rule_fields(self):
        """Each rule should have rule, antipattern, category."""
        result = gauntlet_loop_config("src/")
        if result.error is None:
            for _name, rules in result.rules_by_persona.items():
                for rule in rules:
                    assert "rule" in rule
                    assert "category" in rule
                    assert "antipattern" in rule

    def test_instructions_are_ordered(self):
        """Instructions should be numbered 1-11."""
        result = gauntlet_loop_config("src/")
        if result.error is None:
            assert len(result.instructions) == 11
            assert result.instructions[0].startswith("1.")
            assert result.instructions[-1].startswith("11.")

    def test_issue_format_has_expected_fields(self):
        """Issue format template should have severity, category, etc."""
        result = gauntlet_loop_config("src/")
        assert "severity" in result.issue_format
        assert "category" in result.issue_format
        assert "description" in result.issue_format
        assert "rule_learned" in result.issue_format
        assert "location" in result.issue_format

    def test_prompt_matches_generate_gauntlet_prompt(self):
        """Prompt should be the same as from generate_gauntlet_prompt."""
        loop = gauntlet_loop_config("src/")
        direct = generate_gauntlet_prompt("src/")
        if loop.error is None and direct.error is None:
            assert loop.prompt == direct.prompt

    def test_message_describes_config(self):
        """Message should mention persona count and iterations."""
        result = gauntlet_loop_config("src/")
        if result.error is None:
            assert "personas" in result.message
            assert "10" in result.message


# =============================================================================
# MCP tool wrapper tests
# =============================================================================


class TestBuildlogGauntletPromptMCP:
    """Tests for buildlog_gauntlet_prompt MCP wrapper."""

    def test_returns_dict(self):
        from buildlog.mcp.tools import buildlog_gauntlet_prompt

        result = buildlog_gauntlet_prompt(target="src/")
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        from buildlog.mcp.tools import buildlog_gauntlet_prompt

        result = buildlog_gauntlet_prompt(target="src/")
        assert "prompt" in result
        assert "target" in result
        assert "personas" in result
        assert "total_rules" in result
        assert "error" in result

    def test_filters_persona(self):
        from buildlog.mcp.tools import buildlog_gauntlet_prompt

        result = buildlog_gauntlet_prompt(target="src/", personas=["security_karen"])
        if result.get("error") is None:
            assert result["personas"] == ["security_karen"]

    def test_invalid_persona_error(self):
        from buildlog.mcp.tools import buildlog_gauntlet_prompt

        result = buildlog_gauntlet_prompt(target="src/", personas=["bogus"])
        assert result["error"] is not None


class TestBuildlogGauntletLoopMCP:
    """Tests for buildlog_gauntlet_loop MCP wrapper."""

    def test_returns_dict(self):
        from buildlog.mcp.tools import buildlog_gauntlet_loop

        result = buildlog_gauntlet_loop(target="src/")
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        from buildlog.mcp.tools import buildlog_gauntlet_loop

        result = buildlog_gauntlet_loop(target="src/")
        assert "target" in result
        assert "personas" in result
        assert "max_iterations" in result
        assert "stop_at" in result
        assert "instructions" in result
        assert "issue_format" in result
        # Compact mode (default): prompt + rules_by_persona stripped, valid_rule_ids added
        assert "prompt" not in result
        assert "rules_by_persona" not in result
        assert "valid_rule_ids" in result

    def test_compact_false_includes_full_rules(self):
        from buildlog.mcp.tools import buildlog_gauntlet_loop

        result = buildlog_gauntlet_loop(target="src/", compact=False)
        assert "prompt" in result
        assert "rules_by_persona" in result
        assert "rule_id_index" in result
        assert "valid_rule_ids" not in result

    def test_custom_params_passed(self):
        from buildlog.mcp.tools import buildlog_gauntlet_loop

        result = buildlog_gauntlet_loop(
            target="src/",
            max_iterations=5,
            stop_at="criticals",
            auto_gh_issues=True,
        )
        assert result["max_iterations"] == 5
        assert result["stop_at"] == "criticals"
        assert result["auto_gh_issues"] is True

    def test_invalid_persona_error(self):
        from buildlog.mcp.tools import buildlog_gauntlet_loop

        result = buildlog_gauntlet_loop(target="src/", personas=["bogus"])
        assert result["error"] is not None
