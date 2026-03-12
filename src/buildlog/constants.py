"""Shared constants for buildlog, including the CLAUDE.md integration section."""

# Default name for the per-project buildlog directory.
# Used as the default ``buildlog_dir`` parameter across MCP tools and CLI.
DEFAULT_BUILDLOG_DIR = "buildlog"

# Shorter version for global ~/.claude/CLAUDE.md - focused on "always on" usage
CLAUDE_MD_GLOBAL_SECTION = """
## buildlog (Always On)

buildlog is your ambient data capture layer. It runs in ALL projects via MCP.
Use these tools to track work, extract learnings, and feed downstream systems.

### Core Loop (use after every significant commit)

1. `buildlog_overview()` — check project state
2. `buildlog_commit(message="...")` — git commit with auto entry logging
3. `buildlog_gauntlet_rules()` + review + `buildlog_gauntlet_issues([...])` — run gauntlet
4. `buildlog_log_reward(outcome="accepted")` — close the feedback loop

### Key Tools

| Tool | When to Use |
|------|-------------|
| `buildlog_overview()` | Start of session, check state |
| `buildlog_commit(message)` | Wrap git commits with logging |
| `buildlog_entry_new(slug)` | Create journal entry |
| `buildlog_gauntlet_rules()` | Load reviewer personas |
| `buildlog_gauntlet_issues(issues)` | Process review findings |
| `buildlog_log_reward(outcome)` | Feedback after approval |
| `buildlog_skills()` | Extract patterns from entries |
| `buildlog_status()` | See extracted skills |
| `buildlog_promote(skill_ids)` | Surface to agent rules |

### Outputs (ambient capture for downstream)

- Journal entries: `buildlog/*.md`
- Reward signals: `buildlog/.buildlog/reward_events.jsonl`
- Extracted skills: `buildlog/.buildlog/promoted.json`
- Review learnings: `buildlog/.buildlog/review_learnings.json`
- Emission artifacts: `~/.buildlog/emissions/pending/` (mistake manifests + learned rules for downstream systems)

This data feeds automated content generation, engineering logs, and learning systems.
"""

# Full version for per-project CLAUDE.md - comprehensive reference
CLAUDE_MD_BUILDLOG_SECTION = """
## buildlog Integration

buildlog is configured as an MCP server. Use the tools below to maintain
a learning loop: write entries, extract skills, run gauntlet reviews, and
track experiments.

### Always On: Commit -> Gauntlet -> Learn Loop

After every significant commit or feature completion:

1. **Create/update entry**: `buildlog_entry_new(slug="what-you-built")`
2. **Run gauntlet review**: `buildlog_gauntlet_rules()` to load rules, then review code against them
3. **Process findings**: `buildlog_gauntlet_issues(issues=[...])` to categorize and persist learnings
4. **Fix criticals/majors**, re-run until clean or accept risk: `buildlog_gauntlet_accept_risk(remaining_issues=[...])`
5. **Log reward**: `buildlog_log_reward(outcome="accepted")` when work is approved

### Skill Extraction & Promotion Workflow

1. `buildlog_status()` — see extracted skills by category
2. `buildlog_diff()` — see skills pending review
3. `buildlog_promote(skill_ids=[...], target="claude_md")` — surface to agent rules
4. `buildlog_reject(skill_ids=[...])` — mark false positives

### Gauntlet Review Loop Workflow

1. `buildlog_gauntlet_rules()` — load reviewer persona rules
2. Review code against rules, collect issues
3. `buildlog_gauntlet_issues(issues=[...])` — categorize, persist learnings, get next action
4. If action="fix_criticals": fix and re-run
5. If action="checkpoint_majors"/"checkpoint_minors": ask user
6. `buildlog_gauntlet_accept_risk(remaining_issues=[...])` — accept remaining
7. `buildlog_learn_from_review(issues=[...])` — persist learnings

### Reward Signal / Thompson Sampling Workflow

1. `buildlog_log_reward(outcome="accepted"|"revision"|"rejected")` — explicit feedback
2. `buildlog_rewards()` — view reward history and statistics
3. `buildlog_bandit_status()` — see which rules the bandit favors

### Session Tracking & Experiment Workflow

1. `buildlog_experiment_start(error_class="missing_test")` — begin tracked session
2. `buildlog_log_mistake(error_class="...", description="...")` — log mistakes
3. `buildlog_experiment_end()` — end session, calculate metrics
4. `buildlog_experiment_metrics()` — per-session or aggregate stats
5. `buildlog_experiment_report()` — comprehensive report

### Tool Reference (34 tools)

**Commit & Entries:**
- `buildlog_commit(message, git_args, slug, no_entry)` — git commit with auto buildlog entry
- `buildlog_entry_new(slug, entry_date, quick)` — create entry
- `buildlog_entry_list()` — list all entries
- `buildlog_overview()` — project state at a glance

**Skill Management:**
- `buildlog_status(min_confidence="low")` — extracted skills
- `buildlog_promote(skill_ids, target="claude_md")` — promote to agent rules
- `buildlog_reject(skill_ids)` — reject false positives
- `buildlog_diff()` — pending skills
- `buildlog_distill(since, category)` — extract patterns from entries
- `buildlog_skills(since, min_frequency)` — generate skill set from entries
- `buildlog_stats(since, detailed)` — buildlog statistics and insights

**Gauntlet Review:**
- `buildlog_gauntlet_prompt(target, personas)` — generate review prompt with rules
- `buildlog_gauntlet_loop(target, personas, max_iterations, stop_at, auto_gh_issues)` — full loop config
- `buildlog_gauntlet_rules(persona, format)` — load reviewer rules
- `buildlog_gauntlet_issues(issues, iteration)` — process findings
- `buildlog_gauntlet_accept_risk(remaining_issues)` — accept risk
- `buildlog_gauntlet_list_personas()` — list available reviewer personas
- `buildlog_gauntlet_generate(source_text, persona, dry_run)` — generate rules from source text

**Review Learning:**
- `buildlog_learn_from_review(issues, source)` — persist review learnings

**Reward & Bandit:**
- `buildlog_log_reward(outcome, rules_active)` — log feedback
- `buildlog_rewards(limit)` — reward history
- `buildlog_bandit_status(context)` — bandit state
- `buildlog_posterior_history(rule_ids, persona, since)` — posterior evolution over time

**Experiments:**
- `buildlog_experiment_start(error_class)` — start session
- `buildlog_experiment_end()` — end session
- `buildlog_log_mistake(error_class, description)` — log mistake
- `buildlog_experiment_metrics(session_id)` — metrics
- `buildlog_experiment_report()` — full report

**Project Setup:**
- `buildlog_init(no_mcp, no_claude_md)` — initialize buildlog in project
- `buildlog_update()` — update buildlog template to latest
- `buildlog_migrate(dry_run)` — migrate legacy JSON/JSONL files to global SQLite DB
- `buildlog_export(format, output, project, tables)` — export data to JSONL files
- `buildlog_import_seed(source, target_dir, buildlog_dir)` — import external seed files with version-aware decay
- `buildlog_ingest_seeds(source, buildlog_dir)` — ingest pending seeds from shared directory protocol
- `buildlog_verify(buildlog_dir)` — verify workflow setup (CLAUDE.md, MCP, hooks, branch)

### When to Use Each Tool

- **At session start**: `buildlog_overview()` for context
- **During active dev**: `buildlog_entry_new()` to document work
- **After commits**: `buildlog_commit()` or `buildlog_gauntlet_prompt()` + review + `buildlog_gauntlet_issues()`
- **After review approval**: `buildlog_log_reward(outcome="accepted")`
- **For learning**: `buildlog_distill()`, `buildlog_skills()`, `buildlog_stats()`
- **For skill promotion**: `buildlog_status()` -> `buildlog_diff()` -> `buildlog_promote()`
- **To accept risk**: `buildlog_gauntlet_accept_risk()`
- **For experiments**: `buildlog_experiment_start()` -> work -> `buildlog_experiment_end()`

### Integration with Commits

`buildlog commit -m "message"` wraps git commit and auto-logs to today's entry.

### Reference Files

- `buildlog/.buildlog/promoted.json` — promoted skill IDs
- `buildlog/.buildlog/rejected.json` — rejected skill IDs
- `buildlog/.buildlog/review_learnings.json` — review-based learnings
- `buildlog/.buildlog/reward_events.jsonl` — reward signals
- `buildlog/.buildlog/sessions.jsonl` — session tracking
- `buildlog/.buildlog/mistakes.jsonl` — mistake tracking
- `buildlog/.buildlog/active_session.json` — current session
- `buildlog/bandit_state.jsonl` — Thompson Sampling state
"""

# Workflow enforcement section for CLAUDE.md
# Injected by `buildlog init` and refreshed by `buildlog update`.
# Uses marker-based replacement so it can be updated independently of rules.
_WORKFLOW_SECTION_START = "<!-- buildlog:workflow:start -->"
_WORKFLOW_SECTION_END = "<!-- buildlog:workflow:end -->"

CLAUDE_MD_WORKFLOW_SECTION = f"""{_WORKFLOW_SECTION_START}

## Standard Development Workflow (buildlog-enforced)

Every feature, fix, or refactor follows this loop. No exceptions.

### 1. Issue + Branch
- Create or pick a GitHub issue
- Branch from main: `git checkout -b feat/short-name` or `fix/short-name`
- **Never commit directly to main**

### 2. Implement with Ceremony
- After every substantial change: `buildlog_commit(message="...")`
- Create journal entries: `buildlog_entry_new(slug="what-you-built")`
- The data matters as much as the code

### 3. Gauntlet Review
- `buildlog_gauntlet_loop()` — run the full review loop
- Fix criticals and majors before proceeding
- Accept or file issues for remaining minors

### 4. Pull Request
- Push branch, create PR closing the issue
- PR body: summary, test plan, files changed

### 5. Feedback Loop
- `buildlog_log_reward(outcome="accepted")` after merge
- Reward signal feeds Thompson Sampling for future rule selection

### Key Principles
- **Branch protection**: pre-commit hook prevents commits to main
- **buildlog_commit > git commit**: wraps git commit with journal updates
- **Data is the point**: every commit generates signal for learning systems

{_WORKFLOW_SECTION_END}"""
