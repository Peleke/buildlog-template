# Interop & Seed Ingestion

buildlog can ingest seed files from external producers using a shared directory protocol. Any tool that drops YAML files into the agreed-upon layout works — qortex is the default, but the protocol is producer-agnostic.

## The Directory Protocol

```
~/.qortex/seeds/pending/    <- producer drops files here
~/.qortex/seeds/processed/  <- consumer moves here on success
~/.qortex/seeds/failed/     <- consumer moves here on failure (+ .error sidecar)
~/.qortex/signals/projections.jsonl  <- optional append-only signal log
```

The producer writes seed YAML files to `pending/`. The consumer (buildlog) picks them up, validates, imports, and moves them to either `processed/` or `failed/`.

## Quick Start

```bash
# Ingest all pending files from the default qortex source
buildlog ingest-seeds

# Filter to a specific source
buildlog ingest-seeds --source qortex

# JSON output for scripting
buildlog ingest-seeds --json
```

Or via MCP:

```
buildlog_ingest_seeds()
buildlog_ingest_seeds(source="qortex")
```

## Seed File Format

Seed files are standard buildlog YAML seed files:

```yaml
persona: security_karen
version: "1.0"
provenance:
  source: qortex
  graph_version: "2026-02-05T00:00:00Z"
rules:
  - id: sk-001
    rule: "Always validate user input at API boundaries"
    category: security
    severity: critical
```

See the [seed format documentation](https://github.com/Peleke/buildlog-template) for the full schema.

## Security Validation

The pending directory is a hot injection point — agents read these files. buildlog applies 7 layers of validation:

| Layer | Check | Action on Failure |
|-------|-------|-------------------|
| 1 | Symlink rejection | Skip (not moved) |
| 2 | Filename sanitization (`^[a-zA-Z0-9_.-]+\.ya?ml$`) | Skip (not moved) |
| 3 | File size limit (default 1 MB) | Move to `failed/` |
| 4 | Extension check (`.yaml` / `.yml` only) | Covered by layer 2 |
| 5 | YAML `safe_load` (no code execution) | Move to `failed/` |
| 6 | Schema validation | Move to `failed/` |
| 7 | Content size limits (rules count, text length) | Move to `failed/` |

Failed files get a `.error` JSON sidecar:

```json
{
  "file": "bad-seed.yaml",
  "error": "file too large: 2097152 bytes (max 1048576)",
  "timestamp": "2026-02-05T12:00:00+00:00"
}
```

## Configuration

By default, buildlog scans the qortex directory layout shown above. To configure additional sources or adjust limits, create `~/.buildlog/interop.yaml`:

```yaml
sources:
  - name: qortex
    pending_dir: ~/.qortex/seeds/pending
    processed_dir: ~/.qortex/seeds/processed
    failed_dir: ~/.qortex/seeds/failed
    signal_log: ~/.qortex/signals/projections.jsonl

  - name: custom-producer
    pending_dir: /opt/seeds/incoming
    processed_dir: /opt/seeds/done
    failed_dir: /opt/seeds/errors

max_file_size: 1048576        # bytes (default 1 MB)
max_rules_per_file: 500       # max rules per seed file
max_rule_text_length: 10000   # max chars per rule text
```

All paths support `~` expansion.

## Signal Log

When `signal_log` is configured for a source, buildlog appends JSONL events for each file processed:

```json
{"type": "seed_ingested", "file": "security_karen.yaml", "persona": "security_karen", "rule_count": 12, "timestamp": "..."}
{"type": "seed_failed", "file": "bad.yaml", "error": "Invalid YAML or schema", "timestamp": "..."}
{"type": "seed_skipped", "file": "link.yaml", "error": "symlink rejected", "timestamp": "..."}
```

This log is append-only and can be consumed by downstream systems for observability.

## Version-Aware Bandit Decay

When a seed file is re-imported with a changed `provenance.graph_version`, buildlog triggers 50% decay of learned bandit signal for affected rules. This ensures that when upstream rule definitions change, the bandit doesn't over-rely on stale effectiveness data.

## Writing a Producer

Any tool can be a producer. The contract is simple:

1. Write valid seed YAML files to `~/.qortex/seeds/pending/` (or your configured path)
2. Use safe filenames: alphanumeric, hyphens, underscores, dots, ending in `.yaml` or `.yml`
3. Don't create symlinks in the pending directory
4. The consumer will move files out of `pending/` — don't expect them to stay

That's it. No dependency on buildlog required.
