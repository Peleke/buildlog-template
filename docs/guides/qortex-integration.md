# Qortex Integration: Bidirectional Data Flow

buildlog captures what the agent *did wrong*. Qortex captures what the agent *should know*. The ambient emission protocol closes this loop.

## Data Flow

```
qortex (KG)                         buildlog
  │                                    │
  │  ── project rules (seeds) ──────>  │  ingest via buildlog_import_seed()
  │                                    │
  │                                    │  agent works, makes mistakes,
  │                                    │  learns from reviews
  │                                    │
  │  <── learned_rules emission ─────  │  learn_from_review() emits seed
  │  <── mistake_manifest emission ──  │  log_mistake() emits manifest
  │                                    │
  └────────────────────────────────────┘
```

**Inbound** (qortex → buildlog): Projected rules arrive as YAML seed files via `buildlog_import_seed()` or `buildlog_ingest_seeds()`. These become bandit arms that Thompson Sampling selects from during experiment sessions.

**Outbound** (buildlog → qortex): Two emission types flow to `~/.buildlog/emissions/pending/` for offline ingestion.

## Emission Protocol

### Directory Convention

```
~/.buildlog/emissions/
├── pending/          # new artifacts (buildlog writes here)
├── processed/        # consumer moves files here after ingestion
├── failed/           # consumer moves files here on failure (+ .error sidecar)
└── signal.jsonl      # append-only event log
```

### Signal Log

Each emission appends a JSONL entry:

```json
{"event": "emitted", "type": "mistake_manifest", "project_id": "abc123", "path": "...", "ts": "2026-02-06T12:00:00Z", "source": "buildlog"}
```

Consumers can tail this file for real-time notification or poll `pending/` directly.

### File Naming

```
{artifact_type}_{project_id}_{ISO-timestamp}.json
```

Example: `mistake_manifest_proj-abc_20260206T120000.json`

## Path A: Learned Rules as Seeds

When `learn_from_review()` creates new learnings, it emits a `learned_rules` artifact that conforms to the qortex seed schema:

```json
{
  "persona": "buildlog_proj-abc",
  "version": 1,
  "rules": [
    {
      "rule": "Validate invariants at function boundaries",
      "category": "architectural",
      "provenance": {
        "id": "bl:arch-abc123",
        "domain": "experiential",
        "derivation": "explicit",
        "confidence": 0.7
      }
    }
  ],
  "metadata": {
    "source": "buildlog",
    "source_version": "0.12.0",
    "projected_at": "2026-02-06T12:00:00Z",
    "rule_count": 1
  }
}
```

Confidence is computed as `min(1.0, reinforcement_count * 0.3 + 0.4)`.

## Path B: Mistakes as Manifests

When `log_mistake()` records an enriched mistake, it emits a `mistake_manifest` artifact structured for knowledge graph ingestion:

```json
{
  "source_id": "buildlog:proj-abc",
  "domain": "experiential",
  "concepts": [
    {
      "name": "mistake:mistake-missing_test-20260206T120000",
      "domain": "experiential",
      "properties": {
        "error_class": "missing_test",
        "description": "Forgot to test edge cases",
        "severity": "high",
        "context": "writing new API endpoint"
      },
      "source_id": "buildlog:proj-abc"
    }
  ],
  "edges": [
    {"source_id": "mistake:...", "target_id": "testing", "relation_type": "uses", "confidence": 0.8},
    {"source_id": "mistake:...", "target_id": "rule-1", "relation_type": "challenges", "confidence": 0.7}
  ],
  "rules": [
    {"rule": "Always test edge cases", "category": "missing_test", "provenance": {"domain": "experiential"}}
  ],
  "metadata": {
    "source": "buildlog",
    "source_version": "0.12.0",
    "emitted_at": "2026-02-06T12:00:00Z",
    "project_id": "proj-abc",
    "mistake_id": "mistake-missing_test-20260206T120000"
  }
}
```

### Edge Type Mapping

The manifest includes edges produced by 6 pluggable mappers:

| Mapper | Relation | Source → Target | Fires when |
|--------|----------|-----------------|------------|
| `concept_involvement` | `uses` | mistake → concept | `related_concepts` non-empty |
| `rule_challenge` | `challenges` | mistake → rule | session had `selected_rules` |
| `rule_support` | `supports` | mistake → rule | `corrected_by_rule` set |
| `mistake_chain` | varies | mistake → prior mistake | `relation_to_prior` set |
| `resolution_rule` | — | emits ExplicitRule | `resolution_action` set |
| `resolution_edges` | `implements` + `supports` | resolution → mistake/rule | `resolution_action` set |

#### Chain Type Mapping

`relation_to_prior.type` maps to edge relations:

| Chain type | Edge relation |
|-----------|---------------|
| `escalation` | `refines` |
| `same_pattern` | `similar_to` |
| `regression` | `contradicts` |
| `caused_by` | `requires` |
| `part_of` | `part_of` |
| (unknown) | `similar_to` |

### Mapper Configuration

All mappers are enabled by default. Disable specific mappers via `~/.buildlog/emissions.yaml`:

```yaml
disabled_mappers:
  - resolution_edges
```

The `EdgeMapperRegistry` is the extension point for custom mappers.

## Schema v2 Fields

The enriched mistakes schema adds 5 nullable columns:

| Field | Type | Purpose |
|-------|------|---------|
| `related_concepts` | JSON array | Concept names involved in the mistake |
| `relation_to_prior` | JSON object | `{"id": "...", "type": "escalation\|same_pattern\|..."}` |
| `resolution_action` | text | What fixed the mistake |
| `context` | text | What the agent was doing |
| `severity` | text | `low\|medium\|high\|critical` |

All fields are optional — existing code that calls `log_mistake()` without them continues to work identically.

## Consumer Protocol

To process emissions:

1. List files in `~/.buildlog/emissions/pending/`
2. Parse JSON, validate against expected schema
3. Ingest into your system
4. Move processed files to `processed/` (or `failed/` with `.error` sidecar)
5. Optionally tail `signal.jsonl` for real-time triggers

Emissions are **fire-and-forget** from buildlog's perspective. Emission failure never breaks the primary operation (`log_mistake()`, `learn_from_review()`).
