"""Shared constants for buildlog, including the CLAUDE.md integration section."""

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

### Tool Reference

**Skill Management:**
- `buildlog_status(min_confidence="low")` — extracted skills
- `buildlog_promote(skill_ids, target="claude_md")` — promote to agent rules
- `buildlog_reject(skill_ids)` — reject false positives
- `buildlog_diff()` — pending skills

**Review & Learning:**
- `buildlog_learn_from_review(issues, source)` — persist review learnings
- `buildlog_gauntlet_rules(persona, format)` — load reviewer rules
- `buildlog_gauntlet_issues(issues, iteration)` — process findings
- `buildlog_gauntlet_accept_risk(remaining_issues)` — accept risk

**Reward & Bandit:**
- `buildlog_log_reward(outcome, rules_active)` — log feedback
- `buildlog_rewards(limit)` — reward history
- `buildlog_bandit_status(context)` — bandit state

**Experiments:**
- `buildlog_experiment_start(error_class)` — start session
- `buildlog_experiment_end()` — end session
- `buildlog_log_mistake(error_class, description)` — log mistake
- `buildlog_experiment_metrics(session_id)` — metrics
- `buildlog_experiment_report()` — full report

**Entries & Overview:**
- `buildlog_overview()` — project state at a glance
- `buildlog_entry_new(slug, entry_date, quick)` — create entry
- `buildlog_entry_list()` — list all entries

### When to Use Each Tool

- **At session start**: `buildlog_overview()` for context
- **During active dev**: `buildlog_entry_new()` to document work
- **After commits**: `buildlog_gauntlet_rules()` + review + `buildlog_gauntlet_issues()`
- **After review approval**: `buildlog_log_reward(outcome="accepted")`
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
