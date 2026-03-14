# Troubleshooting

Each section below has a symptom, likely cause, and fix.

---

## MCP Server

### Claude Code doesn't see buildlog tools

**Symptom:** `claude mcp list` doesn't show buildlog, or shows it as disconnected.

**Check:**

```bash
claude mcp list
# Expected: buildlog - Connected
```

**Fixes:**

1. Make sure buildlog is installed and the `buildlog-mcp` command is on your PATH:
   ```bash
   which buildlog-mcp
   # Should print a path. If not, reinstall:
   pipx install buildlog
   ```

2. Re-register the MCP server:
   ```bash
   buildlog init-mcp --global -y
   ```

3. Restart Claude Code. MCP server changes require a restart to take effect.

4. If you installed with `pipx` or `uv tool`, make sure the tool's bin directory is in your PATH. Check:
   ```bash
   pipx list | grep buildlog
   ```

### MCP registered but tools not working

**Symptom:** `claude mcp list` shows buildlog as connected, but calling tools returns errors or hangs.

**Check:**

```bash
buildlog mcp-test
```

This invokes the MCP server directly and lists all 36 tools. If it errors, the problem is in the server.

**Fixes:**

1. Check your Python version. buildlog requires 3.11+:
   ```bash
   python3 --version
   ```

2. Check for conflicting installs. If you installed both globally (`pipx`) and locally (`pip install -e .`), the wrong version might be on PATH:
   ```bash
   which buildlog-mcp
   pip show buildlog
   ```

3. Check that `mcp` is installed (it's a default dependency since v0.10.0):
   ```bash
   python3 -c "import mcp; print(mcp.__version__)"
   ```

### Tools available but buildlog_dir errors

**Symptom:** Tools return `"error": "No buildlog directory found at buildlog"`.

**Cause:** The MCP server's working directory doesn't match your project directory. This happens when Claude Code launches the MCP server from a different directory.

**Fix:** This is normal in global mode for projects that haven't been initialized. Run `buildlog init --defaults` in the project, or use `buildlog overview` (which handles missing directories gracefully and returns empty state instead of erroring).

---

## Extraction Pipeline

### `buildlog distill` produces nothing

**Symptom:** Running distill returns 0 patterns even though you have entries.

**Causes and fixes:**

1. **Entries don't have an Improvements section.** The regex extractor looks for lines matching `- **category**: Rule text` under a `## Improvements` heading. Check your entry format:
   ```markdown
   ## Improvements
   - **architectural**: Always define interfaces before implementations
   ```
   The `**category**` must be one of: `architectural`, `workflow`, `tool_usage`, `domain_knowledge`.

2. **Entries are empty templates.** If you created entries but never filled them in, there's nothing to extract. Open the entry files in `buildlog/` and check.

3. **Wrong date filter.** If you passed `--since`, make sure the date is correct:
   ```bash
   buildlog distill --since 2026-01-01
   ```

4. **Entry filenames don't match the expected pattern.** Entries must be named `YYYY-MM-DD-slug.md` (e.g., `2026-02-13-auth-api.md`). Other filenames are ignored.

### `buildlog skills` shows 0 skills

**Symptom:** Distill finds patterns, but skills returns nothing.

**Cause:** The `--min-frequency` filter (default: 1) is set higher than your pattern count, or no patterns passed deduplication.

**Fix:** Run with explicit min_frequency:
```bash
buildlog skills --min-frequency 1
```

### Skills have "low" confidence

**Symptom:** All skills show `confidence: low` even after many entries.

**Cause:** Confidence is based on frequency (how many entries mention the same pattern) and recency. With few entries or patterns seen only once, confidence stays low.

**Fix:** This is normal early on. Confidence increases as patterns are reinforced across multiple entries. Keep documenting your work.

---

## Promotion

### `buildlog promote` doesn't write to CLAUDE.md

**Symptom:** Command reports success but CLAUDE.md is unchanged.

**Causes and fixes:**

1. **CLAUDE.md doesn't exist.** Promote expects the file to exist. Create it:
   ```bash
   touch CLAUDE.md
   buildlog promote arch-a1b2c3d4e5 --target claude_md
   ```

2. **Wrong target.** Check you're using the right target for your agent:
   ```bash
   buildlog promote arch-a1b2c3d4e5 --target claude_md    # Claude Code
   buildlog promote arch-a1b2c3d4e5 --target cursor        # Cursor
   buildlog promote arch-a1b2c3d4e5 --target copilot       # GitHub Copilot
   ```

3. **Skill IDs are wrong.** IDs are case-sensitive hex strings like `arch-a1b2c3d4e5`. Copy them from `buildlog status` or `buildlog diff` output. Empty strings and whitespace-only IDs are silently filtered out.

### Promoted rules disappear from CLAUDE.md

**Symptom:** Rules were in CLAUDE.md but are gone after an edit.

**Cause:** The rules section is delimited by HTML comment markers:
```markdown
<!-- buildlog:rules:start -->
...rules here...
<!-- buildlog:rules:end -->
```

If you (or your editor) deleted these markers, buildlog can't find the section and may recreate it or skip writing.

**Fix:** Check CLAUDE.md for the markers. If missing, delete any stale rules section and re-promote:
```bash
buildlog promote arch-a1b2c3d4e5 --target claude_md
```

---

## Thompson Sampling / Bandit

### Experiment RMR is always 100%

**Symptom:** Every experiment report shows Repeated Mistake Rate at 100%.

**Cause:** Every mistake you're logging matches a prior mistake. Possible causes:

1. **Error classes are too broad.** If every mistake uses the same error class (e.g., `"bug"`), they'll all match each other. Use specific error classes:
   ```bash
   # Too broad:
   buildlog experiment log-mistake --error-class "bug" --description "..."

   # Better:
   buildlog experiment log-mistake --error-class "null-handling" --description "..."
   buildlog experiment log-mistake --error-class "missing-test" --description "..."
   ```

2. **You're actually repeating the same mistakes.** The high RMR means the current rules haven't prevented those mistakes yet. Log reward signals and let the bandit adapt.

### Experiment RMR is always 0%

**Symptom:** RMR never increases regardless of mistakes logged.

**Cause:** No prior mistakes exist to match against. RMR requires at least two sessions with overlapping error classes to detect repeats.

**Fix:** Run multiple experiment sessions:
```bash
# Session 1
buildlog experiment start --error-class "type-errors"
buildlog experiment log-mistake --error-class "type-errors" --description "Forgot null check"
buildlog experiment end

# Session 2
buildlog experiment start --error-class "type-errors"
buildlog experiment log-mistake --error-class "type-errors" --description "Another null check miss"
buildlog experiment end

# Now RMR should be non-zero
buildlog experiment report
```

### Bandit always selects the same rules

**Symptom:** `buildlog experiment start` selects the same rules every time.

**Cause:** Seed rules start with boosted priors. With few observations, the boosted rules dominate because their distributions are concentrated at higher values. Thompson Sampling needs data to differentiate.

**Fix:** Log more feedback. The system needs reward signals to update posteriors:
```bash
buildlog log-reward --outcome accepted --rules-active arch-a1b2c3d4e5
buildlog log-reward --outcome rejected --rules-active wf-f6g7h8i9j0
```

After ~20 observations per context, you'll see meaningful differentiation. The system is deliberately conservative with limited data to avoid discarding rules prematurely.

### `buildlog bandit-status` shows empty state

**Symptom:** No contexts, no arms, no observations.

**Cause:** The bandit hasn't been used yet. State is only created when:

1. `buildlog experiment start` selects rules (creates arms)
2. `buildlog log-reward` updates arms
3. Gauntlet review with `select_k` parameter selects rules

**Fix:** Run an experiment session or use the gauntlet with Thompson Sampling:
```bash
buildlog experiment start --error-class "my-context"
```

---

## Learning Backend

### `ImportError: qortex is required`

**Symptom:** Setting `BUILDLOG_LEARNING_BACKEND=qortex` produces an ImportError.

**Fix:** Install the qortex extra:
```bash
pip install buildlog[qortex]
```

Requires Python 3.11+. If you're on 3.10, use the builtin backend.

### Unknown backend warning, falls back to builtin

**Symptom:** Log shows `WARNING: Unknown BUILDLOG_LEARNING_BACKEND='...'`.

**Cause:** Typo in the env var value. Valid values are `"builtin"` and `"qortex"` (case-sensitive, lowercase).

**Fix:**
```bash
export BUILDLOG_LEARNING_BACKEND=builtin   # correct
export BUILDLOG_LEARNING_BACKEND=qortex    # correct
export BUILDLOG_LEARNING_BACKEND=Qortex    # wrong - case sensitive
```

### Bandit state lost after switching backends

**Symptom:** You switched from builtin to qortex (or back) and the bandit starts fresh.

**Cause:** Each backend stores state independently. Switching backends starts with fresh priors on the new backend. Your old state is preserved and will be used if you switch back.

**Fix:** If this is a problem, pick one backend and stay with it. If you're early in your usage (few observations), the fresh start has minimal impact.

---

## Seeds

### Seed file rejected during import

**Symptom:** `buildlog import-seed` returns an error.

**Common causes:**

1. **Missing `rule` field.** Every rule must have at least a `rule` key:
   ```yaml
   rules:
     - rule: "Parameterize all SQL queries"    # required
       category: security                       # optional
   ```

2. **Invalid YAML syntax.** Check for tabs (YAML requires spaces), missing colons, or unclosed quotes.

3. **File too large.** Default limit is 1 MB. For the interop protocol, this is configurable in `~/.buildlog/interop.yaml`.

4. **`provenance` is not a dict.** If present, provenance must be a YAML mapping:
   ```yaml
   # Correct:
   provenance:
     id: "my-rule-id"
     graph_version: "v2"

   # Wrong:
   provenance: "some string"
   ```

### `buildlog ingest-seeds` finds no pending files

**Symptom:** Ingest returns "No pending directory" or "No pending files".

**Fixes:**

1. Check the default pending directory exists:
   ```bash
   ls ~/.qortex/seeds/pending/
   ```

2. If using a custom source, check `~/.buildlog/interop.yaml` for the correct `pending_dir` path.

3. Verify files have `.yaml` or `.yml` extension. Other extensions are ignored.

4. Symlinks in the pending directory are rejected for security. Use actual files.

### Seed ingest moves files to failed/

**Symptom:** Files appear in the `failed/` directory with `.error` sidecar files.

**Debug:** Read the `.error` sidecar:
```bash
cat ~/.qortex/seeds/failed/my-rules.yaml.error
```

```json
{
  "file": "my-rules.yaml",
  "error": "Too many rules: 600 (max 500)",
  "timestamp": "2026-02-13T14:30:00+00:00"
}
```

The error message tells you exactly what went wrong. Common issues:
- Too many rules per file (default max: 500)
- Rule text too long (default max: 10,000 chars)
- Invalid YAML or schema

---

## Storage

### `buildlog migrate` says "Nothing to do"

**Symptom:** You expected data to migrate but nothing happened.

**Causes:**

1. **Already migrated.** Legacy files are renamed to `*.migrated` after migration. Check if your files already have this suffix.

2. **No legacy files exist.** If you're on a fresh install, there's nothing to migrate. The global SQLite database was created automatically.

3. **Wrong directory.** `buildlog migrate` looks for `.buildlog/` inside the `buildlog/` directory. Make sure you're in the project root:
   ```bash
   ls buildlog/.buildlog/
   ```

**Fix:** Run with dry-run to see what buildlog finds:
```bash
buildlog migrate --dry-run
```

### "Found un-migrated local data" warning

**Symptom:** Warning about un-migrated data in the `.buildlog/` directory.

**Cause:** The global SQLite database exists, but you have legacy JSON/JSONL files that haven't been migrated. buildlog will use SQLite and ignore the legacy files.

**Fix:** Run `buildlog migrate` to bring legacy data into the global database. Or ignore the warning if you don't need the legacy data.

### Export produces empty files

**Symptom:** `buildlog export` creates files but they're empty.

**Cause:** No data exists for the current project in the database. This happens if:

1. The project was just initialized and no work has been done
2. You're in a different directory than expected (different project ID)

**Fix:** Check what project ID buildlog thinks you're in:
```bash
buildlog overview --json
```

The `project_id` field tells you which project's data you're accessing.

---

## Gauntlet Review

### Gauntlet finds no personas

**Symptom:** `buildlog gauntlet-list-personas` returns empty or errors.

**Cause:** Seed files are missing. buildlog looks for them in:

1. `.buildlog/seeds/`
2. `buildlog/.buildlog/seeds/`
3. Package bundled seeds

**Fix:** If you installed buildlog correctly, package seeds should be available. Check:
```bash
buildlog gauntlet-list-personas
```

If empty, try reinstalling:
```bash
pip install --force-reinstall buildlog
```

### Gauntlet loop never reaches "clean"

**Symptom:** The gauntlet keeps finding issues iteration after iteration.

**Cause:** The code may have issues that require multiple iterations to resolve. It can also happen if:

1. **Fixes introduce new issues.** Each fix is itself code that gets reviewed on the next iteration.
2. **max_iterations is too low.** The default is 10, which should be plenty.

**Fix:** Use `stop_at` to control when to stop:
```bash
buildlog gauntlet-loop --target src/ --stop_at criticals  # stop after clearing criticals only
buildlog gauntlet-loop --target src/ --stop_at majors     # stop after clearing criticals + majors
```

Accept remaining issues as risk:
```bash
buildlog gauntlet-accept-risk --remaining-issues '[...]'
```

### Citation validation strips all rule IDs

**Symptom:** `citation_stats` shows many hallucinated IDs, `rules_credited` is empty.

**Cause:** The LLM is inventing rule IDs instead of using the ones from the prompt. This happens when the prompt doesn't include the `valid_rule_ids` list clearly enough.

**Fix:** Use `buildlog_gauntlet_loop()` which generates the prompt with rule IDs embedded, and pass `valid_rule_ids` to `buildlog_gauntlet_issues()`:
```python
config = buildlog_gauntlet_loop(target="src/")
# ... review code, collect issues ...
result = buildlog_gauntlet_issues(
    issues=[...],
    valid_rule_ids=config["valid_rule_ids"]  # pass this
)
```

---

## CLI / General

### `buildlog commit` fails with "not a git repository"

**Symptom:** `buildlog commit -m "..."` errors about git.

**Cause:** You're not in a git repository, or the `buildlog_dir` doesn't resolve to a directory inside one.

**Fix:** Make sure you're in a git repo:
```bash
git status
```

### Pre-commit hook blocks commits to main

**Symptom:** `git commit` on the main branch is rejected.

**Cause:** buildlog's pre-commit hook prevents direct commits to main. The enforced workflow requires branching.

**Fix:** Create a branch:
```bash
git checkout -b feat/my-feature
git commit -m "my change"
```

If you need to bypass the hook (you shouldn't, but sometimes you must):
```bash
git commit --no-verify -m "emergency fix"
```

### `buildlog verify` reports failures

**Symptom:** `buildlog verify` shows failed checks.

**Fix:** Run verify and address each failure:
```bash
buildlog verify
```

```
PASSED: buildlog/ directory exists
PASSED: CLAUDE.md has workflow section
WARNING: MCP not registered in .claude/settings.json
FAILED: Pre-commit hook not installed
PASSED: Not on main branch

3/5 checks passed, 1 warning, 1 failure
```

For each failure:
- **MCP not registered**: Run `buildlog init-mcp -y` (or `--global -y`)
- **Pre-commit hook not installed**: Run `buildlog init --defaults`
- **CLAUDE.md missing workflow section**: Run `buildlog init --defaults` or manually add the section
- **On main branch**: Switch to a feature branch

### `buildlog overview` shows "not initialized"

**Symptom:** Overview returns `{"initialized": false, ...}`.

**Cause:** No `buildlog/` directory exists in the current project. This is normal in global mode for projects you haven't explicitly initialized.

**Fix:** Either initialize the project:
```bash
buildlog init --defaults
```

Or ignore it. In global mode, buildlog tools work without initialization and return empty state. You only need `buildlog init` if you want to create journal entries in this project.
