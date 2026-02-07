# Build Journal: Rule-Level Attribution for Gauntlet Review (internal/self-ref)

**Date:** 2026-02-06
**Duration:** ~1 hour

## What I Did

Added per-rule, per-issue attribution to the gauntlet review system. Three touches: (1) citable rule IDs in prompts via `get_rule_id()` and `build_rule_id_index()`, (2) citation validation that strips hallucinated rule IDs and logs them as mistakes, (3) bandit update with `reward=1.0` for each credited rule. This closes the feedback loop so Thompson Sampling learns which specific rules actually prevent mistakes, instead of smearing credit equally across all active rules.

Dogfooded the feature during its own gauntlet review — passed `valid_rule_ids` to `buildlog_gauntlet_issues` and got citation stats back. The system reviewed itself.

## What Went Wrong

- Bandit test failed initially because I looked up with context="default" but the update used the issue category as context. Had to understand the bandit's context segmentation model.
- Pre-commit black/isort reformatted the test file on first commit attempt — expected behavior, just needed re-stage.
- Existing test `test_instructions_are_ordered` hardcoded instruction count (8), needed update to 11.

## What I Learned

### Improvements

- The bandit context parameter matters for lookups — always derive test assertions from the same context the production code uses
- Property-based tests for pure functions like `get_rule_id` would catch edge cases (empty strings, unicode) — accepted as minor risk for now
- The gauntlet_loop_config response with 7 personas is enormous — future work could add a summary/lazy-load mode

## Commits

- `c0646f5` feat: add citable rule IDs to gauntlet prompt and config (Touch 1)
- `3375160` feat: citation validation, aggregation, and per-rule bandit credit (Touch 2+3)
- `0e93826` test: add 24 tests for rule-level attribution, update instruction count test
