# LLM Extractor + E2E Gauntlet Dogfood Loop

**Date:** 2026-01-31

## Context

Wired `LLMBackend.extract_rules()` into the seed engine as a proper `RuleExtractor` implementation (`LLMExtractor`). This bridges the LLM module with the seed engine's 4-step pipeline, enabling LLM-assisted rule extraction from arbitrary source content.

Added E2E tests covering the full loop: LLM extraction -> seed YAML generation -> load -> gauntlet learn -> persistence. Also added Ollama smoke tests that hit real local LLM (skipped in CI, runnable locally with `--run-ollama`).

## Decisions

- **LLMExtractor as adapter**: Keeps the extractor hierarchy clean. `llm_extractor.py` is a separate file that imports `LLMBackend` only under `TYPE_CHECKING`, avoiding a hard dependency from the seed engine on the LLM module.
- **confidence=0.7 for LLM rules**: LLM-generated rules are lower confidence than human-curated (1.0). This flows through to seed files and can influence downstream bandit scoring.
- **Placeholder defensibility fields**: When the LLM returns `None` for context/antipattern/rationale, we fill with "Not specified by LLM". This passes `is_complete()` validation but `LLMExtractor.validate()` warns on them, signaling they should be enriched.
- **Pipeline.with_llm() convenience constructor**: Avoids boilerplate when wiring up LLMExtractor + TagBasedCategorizer. Keeps the base Pipeline clean.
- **Ollama smoke tests with skipif**: Real LLM tests are valuable but can't run in CI yet. Using `pytest.mark.skipif` on `_ollama_available()` so they auto-skip when Ollama isn't running, but can be explicitly run locally.

## `buildlog commit` — Entry-Commit Sync

Added `buildlog commit` as a drop-in replacement for `git commit`. It:
1. Runs `git commit` with all forwarded args (`-m`, `--amend`, etc.)
2. Appends a `## Commits` section to today's buildlog entry with hash, message, and changed files
3. Auto-creates an entry if none exists for today (slug derived from branch name)
4. `--no-entry` flag to skip entry update for noise commits
5. `--slug` / `--entry` to control which entry gets updated

This makes the buildlog entry a living document that grows with the commit history, rather than a post-hoc writeup.

## Improvements

- Always define interfaces before implementations — the `RuleExtractor` ABC made adding `LLMExtractor` straightforward without touching existing extractors.
- When bridging two modules (LLM and seed engine), use adapter pattern with `TYPE_CHECKING` imports to avoid circular dependencies.
- Include both mock-based and real-backend smoke tests for LLM integrations. Mock tests verify logic; smoke tests verify the integration actually works end-to-end.

### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —



### `` —
