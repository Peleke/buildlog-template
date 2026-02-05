"""Tests for the shared directory interop protocol (B7)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from buildlog.interop import (
    DEFAULT_SOURCE,
    IngestResult,
    InteropConfig,
    SeedSource,
    _append_signal,
    _validate_pending_file,
    _write_error_sidecar,
    ingest_pending,
    load_interop_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SEED_YAML = textwrap.dedent(
    """\
    persona: test_persona
    version: 1
    rules:
      - rule: "Always validate input"
        category: security
        context: "User-facing endpoints"
        antipattern: "Trusting raw input"
        rationale: "Prevents injection attacks"
        tags: [security, validation]
"""
)

MINIMAL_SEED_YAML = textwrap.dedent(
    """\
    persona: minimal
    version: 1
    rules:
      - rule: "Keep it simple"
"""
)


def _write_seed(
    directory: Path, name: str = "test_persona.yaml", content: str | None = None
) -> Path:
    """Write a seed file and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(content or VALID_SEED_YAML)
    return path


def _make_source(tmp_path: Path, name: str = "test") -> SeedSource:
    """Create a SeedSource rooted in tmp_path."""
    base = tmp_path / name
    return SeedSource(
        name=name,
        pending_dir=base / "pending",
        processed_dir=base / "processed",
        failed_dir=base / "failed",
        signal_log=base / "signals" / "projections.jsonl",
    )


# ===========================================================================
# TestInteropConfig
# ===========================================================================


class TestInteropConfig:
    """Tests for configuration loading."""

    def test_default_config(self, tmp_path, monkeypatch):
        """Returns qortex defaults when no config file exists."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

        config = load_interop_config()
        assert len(config.sources) == 1
        assert config.sources[0].name == "qortex"
        assert config.max_file_size == 1_048_576
        assert config.max_rules_per_file == 500

    def test_load_config_from_file(self, tmp_path, monkeypatch):
        """Parses ~/.buildlog/interop.yaml correctly."""
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        config_dir = tmp_path / ".buildlog"
        config_dir.mkdir()
        config_file = config_dir / "interop.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "sources": [
                        {
                            "name": "custom",
                            "pending_dir": str(tmp_path / "custom" / "pending"),
                            "processed_dir": str(tmp_path / "custom" / "processed"),
                            "failed_dir": str(tmp_path / "custom" / "failed"),
                        }
                    ],
                    "max_file_size": 512_000,
                    "max_rules_per_file": 100,
                }
            )
        )

        config = load_interop_config()
        assert len(config.sources) == 1
        assert config.sources[0].name == "custom"
        assert config.max_file_size == 512_000
        assert config.max_rules_per_file == 100

    def test_multiple_sources(self, tmp_path, monkeypatch):
        """Config with 2+ sources."""
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        config_dir = tmp_path / ".buildlog"
        config_dir.mkdir()
        (config_dir / "interop.yaml").write_text(
            yaml.dump(
                {
                    "sources": [
                        {
                            "name": "alpha",
                            "pending_dir": str(tmp_path / "a" / "pending"),
                            "processed_dir": str(tmp_path / "a" / "processed"),
                            "failed_dir": str(tmp_path / "a" / "failed"),
                        },
                        {
                            "name": "beta",
                            "pending_dir": str(tmp_path / "b" / "pending"),
                            "processed_dir": str(tmp_path / "b" / "processed"),
                            "failed_dir": str(tmp_path / "b" / "failed"),
                            "signal_log": str(tmp_path / "b" / "signals.jsonl"),
                        },
                    ]
                }
            )
        )

        config = load_interop_config()
        assert len(config.sources) == 2
        assert config.sources[0].name == "alpha"
        assert config.sources[1].name == "beta"
        assert config.sources[1].signal_log is not None

    def test_tilde_expansion(self, tmp_path, monkeypatch):
        """~/paths are expanded correctly."""
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        config_dir = tmp_path / ".buildlog"
        config_dir.mkdir()
        (config_dir / "interop.yaml").write_text(
            yaml.dump(
                {
                    "sources": [
                        {
                            "name": "tilde",
                            "pending_dir": "~/seeds/pending",
                            "processed_dir": "~/seeds/processed",
                            "failed_dir": "~/seeds/failed",
                        }
                    ]
                }
            )
        )

        config = load_interop_config()
        src = config.sources[0]
        # Should be expanded — no ~ prefix
        assert "~" not in str(src.pending_dir)


# ===========================================================================
# TestSecurityValidation
# ===========================================================================


class TestSecurityValidation:
    """Tests for the 7-layer security checks."""

    def test_rejects_symlink(self, tmp_path):
        """Symlinked file -> skipped."""
        real = tmp_path / "real.yaml"
        real.write_text(VALID_SEED_YAML)
        link = tmp_path / "link.yaml"
        link.symlink_to(real)

        config = InteropConfig()
        err = _validate_pending_file(link, config)
        assert err is not None
        assert "symlink" in err

    def test_rejects_oversized_file(self, tmp_path):
        """>1MB -> failed."""
        big = tmp_path / "big.yaml"
        big.write_text("x" * (1_048_577))

        config = InteropConfig()
        err = _validate_pending_file(big, config)
        assert err is not None
        assert "too large" in err

    def test_rejects_bad_filename(self, tmp_path):
        """Path-traversal filename -> skipped."""
        bad = tmp_path / "..%2f..%2fetc%2fpasswd.yaml"
        bad.write_text(VALID_SEED_YAML)

        config = InteropConfig()
        err = _validate_pending_file(bad, config)
        assert err is not None
        assert "unsafe filename" in err

    def test_rejects_non_yaml_extension(self, tmp_path):
        """.json, .txt -> skipped."""
        for ext in [".json", ".txt", ".py", ".sh"]:
            p = tmp_path / f"file{ext}"
            p.write_text("content")
            err = _validate_pending_file(p, InteropConfig())
            assert err is not None, f"Should reject {ext}"

    def test_rejects_too_many_rules(self, tmp_path):
        """501 rules -> failed."""
        rules = [{"rule": f"Rule {i}"} for i in range(501)]
        seed_data = {"persona": "spammer", "version": 1, "rules": rules}
        _write_seed(tmp_path / "pending", "spammer.yaml", yaml.dump(seed_data))

        source = _make_source(tmp_path)
        source.pending_dir = tmp_path / "pending"
        config = InteropConfig(sources=[source], max_rules_per_file=500)

        results = ingest_pending(config=config, target_dir=tmp_path / "seeds")
        file_results = results[0].files
        assert any(
            f.status == "failed" and "Too many rules" in (f.error or "")
            for f in file_results
        )

    def test_rejects_oversized_rule_text(self, tmp_path):
        """10001 char rule -> failed."""
        rules = [{"rule": "x" * 10_001}]
        seed_data = {"persona": "verbose", "version": 1, "rules": rules}
        _write_seed(tmp_path / "pending", "verbose.yaml", yaml.dump(seed_data))

        source = _make_source(tmp_path)
        source.pending_dir = tmp_path / "pending"
        config = InteropConfig(sources=[source], max_rule_text_length=10_000)

        results = ingest_pending(config=config, target_dir=tmp_path / "seeds")
        file_results = results[0].files
        assert any(
            f.status == "failed" and "too long" in (f.error or "") for f in file_results
        )

    def test_accepts_valid_file(self, tmp_path):
        """Clean file passes all checks."""
        path = _write_seed(tmp_path, "good.yaml")
        config = InteropConfig()
        err = _validate_pending_file(path, config)
        assert err is None


# ===========================================================================
# TestIngestPending
# ===========================================================================


class TestIngestPending:
    """Tests for the main ingest flow."""

    def test_ingest_happy_path(self, tmp_path):
        """File ingested, moved to processed/."""
        source = _make_source(tmp_path)
        _write_seed(source.pending_dir)
        config = InteropConfig(sources=[source])

        results = ingest_pending(config=config, target_dir=tmp_path / "seeds")
        assert len(results) == 1
        r = results[0]
        assert r.ingested == 1
        assert r.failed == 0
        assert (source.processed_dir / "test_persona.yaml").exists()
        assert not (source.pending_dir / "test_persona.yaml").exists()

    def test_ingest_invalid_yaml(self, tmp_path):
        """Malformed YAML -> moved to failed/ with .error sidecar."""
        source = _make_source(tmp_path)
        _write_seed(source.pending_dir, content="{{not: valid: yaml: [[[")
        config = InteropConfig(sources=[source])

        results = ingest_pending(config=config, target_dir=tmp_path / "seeds")
        r = results[0]
        assert r.failed == 1
        assert (source.failed_dir / "test_persona.yaml").exists()
        assert (source.failed_dir / "test_persona.yaml.error").exists()

    def test_ingest_schema_invalid(self, tmp_path):
        """Valid YAML but bad schema -> moved to failed/."""
        bad_schema = textwrap.dedent(
            """\
            persona: bad
            version: 1
            rules:
              - not_a_rule: "missing 'rule' key"
        """
        )
        source = _make_source(tmp_path)
        _write_seed(source.pending_dir, content=bad_schema)
        config = InteropConfig(sources=[source])

        results = ingest_pending(config=config, target_dir=tmp_path / "seeds")
        r = results[0]
        assert r.failed == 1

    def test_ingest_empty_pending_dir(self, tmp_path):
        """Empty pending dir -> no-op."""
        source = _make_source(tmp_path)
        source.pending_dir.mkdir(parents=True)
        config = InteropConfig(sources=[source])

        results = ingest_pending(config=config, target_dir=tmp_path / "seeds")
        r = results[0]
        assert r.ingested == 0
        assert r.failed == 0
        assert r.skipped == 0

    def test_ingest_nonexistent_pending_dir(self, tmp_path):
        """Nonexistent pending dir -> no-op."""
        source = _make_source(tmp_path)
        # Don't create the pending dir
        config = InteropConfig(sources=[source])

        results = ingest_pending(config=config, target_dir=tmp_path / "seeds")
        r = results[0]
        assert r.ingested == 0
        assert "No pending directory" in r.message

    def test_ingest_multiple_files(self, tmp_path):
        """Processes all files, reports per-file."""
        source = _make_source(tmp_path)
        _write_seed(source.pending_dir, "persona_a.yaml", VALID_SEED_YAML)
        _write_seed(source.pending_dir, "persona_b.yaml", MINIMAL_SEED_YAML)
        config = InteropConfig(sources=[source])

        results = ingest_pending(config=config, target_dir=tmp_path / "seeds")
        r = results[0]
        assert r.ingested == 2
        assert len(r.files) == 2

    def test_ingest_creates_processed_dir(self, tmp_path):
        """mkdir processed/ if missing."""
        source = _make_source(tmp_path)
        _write_seed(source.pending_dir)
        # processed_dir doesn't exist yet
        config = InteropConfig(sources=[source])

        ingest_pending(config=config, target_dir=tmp_path / "seeds")
        assert source.processed_dir.exists()

    def test_ingest_creates_failed_dir(self, tmp_path):
        """mkdir failed/ if missing."""
        source = _make_source(tmp_path)
        _write_seed(source.pending_dir, content="{{bad yaml")
        config = InteropConfig(sources=[source])

        ingest_pending(config=config, target_dir=tmp_path / "seeds")
        assert source.failed_dir.exists()

    def test_ingest_filter_by_source(self, tmp_path):
        """Only processes named source."""
        src_a = _make_source(tmp_path, "alpha")
        src_b = _make_source(tmp_path, "beta")
        _write_seed(src_a.pending_dir, "a.yaml")
        _write_seed(src_b.pending_dir, "b.yaml")
        config = InteropConfig(sources=[src_a, src_b])

        results = ingest_pending(
            config=config, source_name="alpha", target_dir=tmp_path / "seeds"
        )
        assert len(results) == 1
        assert results[0].source == "alpha"
        # beta's file should still be in pending
        assert (src_b.pending_dir / "b.yaml").exists()

    def test_ingest_triggers_version_decay(self, tmp_path):
        """Re-import with changed graph_version triggers decay."""
        source = _make_source(tmp_path)
        seeds_dir = tmp_path / "seeds"
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # First import: version 1
        v1_yaml = textwrap.dedent(
            """\
            persona: evolving
            version: 1
            rules:
              - rule: "Check bounds"
                category: security
                provenance:
                  graph_version: "v1"
        """
        )
        _write_seed(source.pending_dir, "evolving.yaml", v1_yaml)
        config = InteropConfig(sources=[source])
        ingest_pending(config=config, target_dir=seeds_dir, buildlog_dir=buildlog_dir)

        # Second import: version 2 (graph_version changed)
        v2_yaml = textwrap.dedent(
            """\
            persona: evolving
            version: 2
            rules:
              - rule: "Check bounds"
                category: security
                provenance:
                  graph_version: "v2"
        """
        )
        _write_seed(source.pending_dir, "evolving.yaml", v2_yaml)
        results = ingest_pending(
            config=config, target_dir=seeds_dir, buildlog_dir=buildlog_dir
        )
        # Should still ingest successfully
        assert results[0].ingested == 1


# ===========================================================================
# TestSignalLog
# ===========================================================================


class TestSignalLog:
    """Tests for signal log appending."""

    def test_signal_appended_on_ingest(self, tmp_path):
        """projections.jsonl gets seed_ingested event."""
        source = _make_source(tmp_path)
        _write_seed(source.pending_dir)
        config = InteropConfig(sources=[source])

        ingest_pending(config=config, target_dir=tmp_path / "seeds")

        assert source.signal_log.exists()
        lines = source.signal_log.read_text().strip().split("\n")
        events = [json.loads(line) for line in lines]
        assert any(e["type"] == "seed_ingested" for e in events)

    def test_signal_appended_on_failure(self, tmp_path):
        """projections.jsonl gets seed_failed event."""
        source = _make_source(tmp_path)
        _write_seed(source.pending_dir, content="{{bad")
        config = InteropConfig(sources=[source])

        ingest_pending(config=config, target_dir=tmp_path / "seeds")

        assert source.signal_log.exists()
        lines = source.signal_log.read_text().strip().split("\n")
        events = [json.loads(line) for line in lines]
        assert any(e["type"] == "seed_failed" for e in events)

    def test_signal_log_none(self, tmp_path):
        """No-op when signal_log is None."""
        nonexistent = tmp_path / "should_not_exist.jsonl"
        _append_signal(None, {"type": "test"})
        assert not nonexistent.exists()


# ===========================================================================
# TestErrorSidecar
# ===========================================================================


class TestErrorSidecar:
    """Tests for .error sidecar files."""

    def test_error_sidecar_created(self, tmp_path):
        """.error file written next to failed file."""
        failed_path = tmp_path / "bad.yaml"
        failed_path.write_text("content")

        _write_error_sidecar(failed_path, "test error")

        sidecar = tmp_path / "bad.yaml.error"
        assert sidecar.exists()

    def test_error_sidecar_content(self, tmp_path):
        """Contains file, error, timestamp."""
        failed_path = tmp_path / "bad.yaml"
        failed_path.write_text("content")

        _write_error_sidecar(failed_path, "schema invalid")

        sidecar = tmp_path / "bad.yaml.error"
        data = json.loads(sidecar.read_text())
        assert data["file"] == "bad.yaml"
        assert data["error"] == "schema invalid"
        assert "timestamp" in data


# ===========================================================================
# TestMCPTool
# ===========================================================================

# Skip if mcp not installed
pytest.importorskip("mcp")


class TestMCPTool:
    """Tests for the MCP tool wrapper."""

    def test_buildlog_ingest_seeds_happy_path(self, tmp_path):
        """MCP wrapper returns correct dict."""
        from buildlog.mcp.tools import buildlog_ingest_seeds

        source = _make_source(tmp_path)
        _write_seed(source.pending_dir)
        config = InteropConfig(sources=[source])

        with patch("buildlog.interop.load_interop_config", return_value=config):
            result = buildlog_ingest_seeds(buildlog_dir=str(tmp_path / "buildlog"))

        assert "sources" in result
        assert result["total_ingested"] == 1
        assert result["total_failed"] == 0

    def test_buildlog_ingest_seeds_no_pending(self, tmp_path):
        """Empty result when nothing pending."""
        from buildlog.mcp.tools import buildlog_ingest_seeds

        source = _make_source(tmp_path)
        source.pending_dir.mkdir(parents=True)
        config = InteropConfig(sources=[source])

        with patch("buildlog.interop.load_interop_config", return_value=config):
            result = buildlog_ingest_seeds(buildlog_dir=str(tmp_path / "buildlog"))

        assert result["total_ingested"] == 0


# ===========================================================================
# TestCLIIngestSeeds
# ===========================================================================


class TestCLIIngestSeeds:
    """Tests for the CLI ingest-seeds command."""

    def test_cli_happy_path(self, tmp_path):
        """ingest-seeds ingests files and prints summary."""
        from click.testing import CliRunner

        from buildlog.cli import main

        source = _make_source(tmp_path)
        _write_seed(source.pending_dir)
        config = InteropConfig(sources=[source])

        runner = CliRunner()
        with patch("buildlog.interop.load_interop_config", return_value=config):
            result = runner.invoke(
                main,
                ["ingest-seeds", "--buildlog-dir", str(tmp_path / "buildlog")],
            )

        assert result.exit_code == 0
        assert "1 ingested" in result.output

    def test_cli_json_output(self, tmp_path):
        """--json flag produces valid JSON."""
        from click.testing import CliRunner

        from buildlog.cli import main

        source = _make_source(tmp_path)
        _write_seed(source.pending_dir)
        config = InteropConfig(sources=[source])

        runner = CliRunner()
        with patch("buildlog.interop.load_interop_config", return_value=config):
            result = runner.invoke(
                main,
                [
                    "ingest-seeds",
                    "--json",
                    "--buildlog-dir",
                    str(tmp_path / "buildlog"),
                ],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["ingested"] == 1

    def test_cli_no_pending(self, tmp_path):
        """Empty pending dir prints no-op message."""
        from click.testing import CliRunner

        from buildlog.cli import main

        source = _make_source(tmp_path)
        source.pending_dir.mkdir(parents=True)
        config = InteropConfig(sources=[source])

        runner = CliRunner()
        with patch("buildlog.interop.load_interop_config", return_value=config):
            result = runner.invoke(
                main,
                ["ingest-seeds", "--buildlog-dir", str(tmp_path / "buildlog")],
            )

        assert result.exit_code == 0
        assert "No pending files" in result.output
