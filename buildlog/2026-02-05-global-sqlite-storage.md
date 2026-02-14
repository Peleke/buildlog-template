# Build Journal: Global SQLite Storage + qortex Interop + v0.12.0 Release

**Date:** 2026-02-05
**Duration:** 8 hours

## What I Did

Massive infrastructure day. Shipped the global SQLite storage backend with migrate and export commands (#98), v0.11.0 release (#101), ReadTheDocs theme with theory tutorials and roadmap (#102), file param alternatives for MCP tools (#104), qortex interop with provenance and confidence boosting (#105), the B7 shared directory protocol for consumer-side ingest (#106), gauntlet review fixes, and the v0.12.0 release (#109). Fifteen commits in total.

## Commits

- `1939cc2` feat: global SQLite storage backend with migrate + export (#98)
- `c7b521c` chore: release v0.11.0 (#101)
- `593fdea` feat: readthedocs theme + theory tutorial series + roadmap (#102)
- `785ec93` feat: add _file param alternatives to MCP tools (#104)
- `f957dfb` feat: qortex interop — provenance, confidence boosting, import-seed, export expansion (#105)
- `39e70c8` docs: add v0.12.0 changelog for Track E qortex interop
- `41043fe` docs: update tool count 31-32, add import-seed + expanded export docs
- `1996d46` fix: gauntlet review findings — clamp decay_factor, path traversal guard, test gaps
- `48c1f98` feat: B7 shared directory protocol — consumer-side ingest from external producers (#106)
- `76c6248` fix: gauntlet review findings -- extract _fail_file helper, add CLI tests, fix assertion gap
- `40d557b` docs: add interop guide, fix tool count 32-33 across all docs
- `771d02b` docs: add SVG plots to theory tutorials
- `43a71a9` docs: remove 'tutorial' language from theory index
- `6cea850` chore: release v0.12.0
- `6c778dd` Merge pull request #109 from Peleke/chore/release-v0.12.0

## What Went Wrong

The path traversal guard was missing from interop, which the gauntlet caught. Decay factor clamping was also needed to prevent negative values. These are exactly the kind of security and validation issues that automated review catches before they reach production.

## What I Learned

## Improvements

### Architectural

- The StorageBackend protocol pattern (SQLite + Legacy backends behind a common interface) makes migration safe: old and new systems coexist during transition
- Shared directory protocol enables multi-project buildlog aggregation without requiring network services
- Always clamp numeric config values (decay_factor) to valid ranges at the boundary, not deep in business logic

### Workflow

- Running gauntlet review after every major feature PR catches security issues (path traversal) that unit tests miss
- Bundling docs updates with feature releases keeps documentation synchronized with code

### Domain Knowledge

- qortex interop provenance tracking (which system contributed each insight) is essential for debugging cross-system data flows
