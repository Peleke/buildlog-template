# The buildlog Learning Loop: End-to-End Trace

**Date:** 2026-02-14
**Version:** 0.18.1 (buildlog) / 0.5.3 ([qortex](https://github.com/Peleke/qortex))
**Purpose:** Trace every step of the learning loop with explicit code citations proving the narrative.

---

## Table of Contents

1. [Installation & Always-On MCP](#1-installation--always-on-mcp)
2. [Session Start & Thompson Sampling](#2-session-start--thompson-sampling)
3. [Gauntlet Review](#3-gauntlet-review)
4. [Learning from Review](#4-learning-from-review)
5. [Reward & Mistake Logging](#5-reward--mistake-logging)
6. [Bandit Update (The Bayesian Core)](#6-bandit-update-the-bayesian-core)
7. [Skill Promotion & Rule Unification](#7-skill-promotion--rule-unification)
8. [Emission Pipeline (Fire-and-Forget)](#8-emission-pipeline-fire-and-forget)
9. [Marimo Dashboard (What You See)](#9-marimo-dashboard-what-you-see)
10. [qortex Ingestion into Memgraph](#10-qortex-ingestion-into-memgraph)
11. [Cross-Domain Discovery & Rule Re-Export](#11-cross-domain-discovery--rule-re-export)
12. [Memgraph Visualization (What You See)](#12-memgraph-visualization-what-you-see)
13. [The Loop Closes](#13-the-loop-closes)

---

## 1. Installation & Always-On MCP

### What happens

A user runs `buildlog init` in any project. This creates the `buildlog/` directory, registers the MCP server, and optionally patches `CLAUDE.md` with workflow instructions.

### Code path

1. **CLI entry:** `src/buildlog/cli.py:61` — `init()` creates the `buildlog/` directory via copier template, ensures `.buildlog/seeds/` exists (`cli.py:116-118`), and calls `_init_mcp()` to register the MCP server (`cli.py:159-165`).

2. **MCP server registration:** `src/buildlog/mcp/server.py:44` — `mcp = FastMCP("buildlog")` creates the server instance. Lines 47-100 register every tool via `mcp.tool()` decorator. The server exposes 28 tools covering the full lifecycle.

3. **Always-on config:** The user's `~/.claude/CLAUDE.md` includes the `buildlog (Always On)` section. Every Claude Code session, in any project, has access to `buildlog_overview()`, `buildlog_commit()`, `buildlog_gauntlet_loop()`, and `buildlog_log_reward()`. The MCP server starts automatically.

### What the user sees

Nothing visible. buildlog is ambient. It runs in the background. The agent sees the tools in its tool list and the workflow instructions in CLAUDE.md.

---

## 2. Session Start & Thompson Sampling

### What happens

When `buildlog_experiment_start()` is called (via MCP tool `src/buildlog/mcp/tools.py:398`), a tracked session begins. Thompson Sampling selects which gauntlet rules will be "active" for this session.

### Code path

1. **MCP wrapper:** `src/buildlog/mcp/tools.py:398-435` — `buildlog_experiment_start()` delegates to `start_session()`.

2. **Session init:** `src/buildlog/core/operations.py:2072` — `start_session()`:
   - **Line 2105:** `_generate_session_id(now)` — creates a unique ID like `session-20260214-122536-865790`.
   - **Line 2106:** `_get_current_rules(buildlog_dir)` — loads the unified rule pool.

3. **Unified rule pool:** `src/buildlog/core/operations.py:1907-1928` — `_get_current_rules()`:
   - **Line 1918:** `backend.load_id_set(project_id, "promoted")` — loads promoted skill IDs from `skill_decisions` table.
   - **Lines 1921-1926:** `backend.load_gauntlet_rules(active_only=True)` — loads active gauntlet rules (seeds + promoted).
   - **Line 1928:** Returns `sorted(promoted | gauntlet_ids)` — the union of both.

4. **Seed detection with boosted priors:** `src/buildlog/core/operations.py:1931-2000` — `_get_seed_rule_ids()`:
   - **Lines 1973-1998:** Loads gauntlet rules where `persona != "learned"` — these are seed rules from YAML.
   - **Lines 1983-1996:** Extracts confidence from provenance JSON to build a `confidence_map`.
   - **Line 2000:** Returns `(seed_ids, confidence_map)`.

5. **Thompson Sampling selection:** `src/buildlog/core/operations.py:2128-2141`:
   - **Line 2128:** `bandit = get_learning_backend(buildlog_dir)` — gets the `ThompsonSamplingBandit`.
   - **Line 2132:** Calls `_get_seed_rule_ids()` for boosted priors.
   - **Lines 2135-2141:** `bandit.select(candidates, k, context, seed_ids, confidence_map)`.

6. **Inside `select()`:** `src/buildlog/core/bandit.py:606`:
   - **Lines 645-660:** For each candidate rule:
     - **Line 649:** `params = self.state.get_params(ctx, rule_id)` — retrieves `Beta(alpha, beta)`.
     - **Lines 651-656:** New rules get initialized:
       - Seed rules: `Beta(1 + seed_boost, 1)` where `seed_boost` defaults to `2.0` (`bandit.py:101`). This gives seeds a higher starting mean (~0.75 vs 0.50).
       - Learned rules: `Beta(1, 1)` — uniform prior (no preference).
     - **Line 659:** `sample = params.sample()`. We _sample_ from the Beta distribution, not use the mean. High-uncertainty arms occasionally produce high samples, driving exploration.
   - **Lines 662-664:** Sort all candidates by sampled value, return top `k`.
   - **Line 667:** `self._persistence.save()` — persist any new arms created.

7. **Session saved:** `src/buildlog/core/operations.py:2154` — `backend.save_active_session()` persists the session with `selected_rules` and `rules_at_start`.

### What the user sees

The MCP tool returns:
```json
{
  "session_id": "session-20260214-122536-865790",
  "rules_count": 42,
  "selected_rules": ["security_karen:rule:0", "test_terrorist:rule:3", ...],
  "message": "Session started with 42 rules (3 selected via Thompson Sampling)"
}
```

---

## 3. Gauntlet Review

### What happens

The agent reviews target code using persona-based rules. `buildlog_gauntlet_loop()` generates a review prompt with all rules, instructions, and expected issue format. The agent reads the code, finds issues, and reports them with rule citations.

### Code path

1. **MCP wrapper:** `src/buildlog/mcp/tools.py:940-996` — `buildlog_gauntlet_loop()` delegates to `gauntlet_loop_config()`.

2. **Config generation:** `src/buildlog/core/operations.py:4060-4188` — `gauntlet_loop_config()`:
   - **Line 4102:** `load_rules()` — loads seed rules from DB or YAML.
   - **Lines 4107-4113:** Filters by persona names if specified.
   - **Lines 4116-4117:** Optional learning-backend filtering via Thompson Sampling (`select_gauntlet_rules()`).
   - **Lines 4119-4129:** Builds `rules_by_persona` dict mapping each persona to its rule IDs.
   - **Line 4131:** `build_rule_id_index()` — creates an index for citation validation.
   - **Lines 4133-4139:** `generate_gauntlet_prompt()` — creates the review prompt with rules formatted for the agent.
   - **Lines 4163-4171:** Defines the expected issue format: `severity`, `category`, `description`, `rule_learned`, `rules_consulted`, `rule_reasoning`.

3. **Rule loading:** `src/buildlog/seeds.py:665-716` — `load_rules()`:
   - **Line 696-699:** If backend has rules in DB, return those.
   - **Line 702-704:** If DB empty, auto-import from YAML seeds, then return from DB.
   - **Line 708-716:** If no backend (legacy), fall back to `load_all_seeds()`.

4. **Rule loading from DB:** `src/buildlog/storage/sqlite.py:518-535` — `load_gauntlet_rules()`:
   - **Line 532-535:** `SELECT * FROM gauntlet_rules` with optional `WHERE persona = ?` and `WHERE active = 1` filters.

### What the user sees

The agent gets a structured prompt containing all rules grouped by persona (security_karen, test_terrorist, bragi, etc.), then reviews `src/` or whatever target was specified.

---

## 4. Learning from Review

### What happens

After the agent reports issues, `buildlog_gauntlet_issues()` processes them: validates rule citations, persists learnings, credits cited rules via bandit updates, and determines the next action.

### Code path

1. **MCP wrapper:** `src/buildlog/mcp/tools.py:616-706` — `buildlog_gauntlet_issues()` delegates to `gauntlet_process_issues()`.

2. **Issue processing:** `src/buildlog/core/operations.py:2924-3066` — `gauntlet_process_issues()`:
   - **Lines 2949-3002:** **Citation validation**: For each issue's `rules_consulted`:
     - Counts valid citations against `valid_rule_ids`.
     - Detects hallucinated IDs (cited rules that don't exist).
     - **Logs hallucinations as mistakes:** `log_mistake(...error_class="citation_hallucination"...)`. The system catches the agent lying.
   - **Lines 3004-3007:** Categorizes issues by severity (critical/major/minor/nitpick).
   - **Line 3011:** `learn_from_review(buildlog_dir, issues, learn_source)` — persists learnings.
   - **Lines 3019-3027:** **Bandit credit (positive feedback):**
     - For each credited rule: `bandit.update(rule_id, reward=1.0, context=None)`.
     - This teaches the bandit: "this rule was useful, the agent cited it to find a real issue."

3. **Learning persistence:** `src/buildlog/core/operations.py:997-1120` — `learn_from_review()`:
   - **Line 1042:** `backend.load_learnings(project_id)` — loads existing learnings.
   - **Lines 1048-1090:** For each issue's `rule_learned`:
     - **Line 1056:** `_generate_learning_id(category, rule)` — deterministic ID using same hash scheme as skills (`skills.py:217-233`).
     - **Lines 1058-1071:** If learning already exists: **reinforce** (increment `reinforcement_count`, update `last_reinforced`).
     - **Lines 1072-1087:** If new: create `ReviewLearning` with initial metrics.
   - **Line 1103:** `backend.save_learnings(project_id, data)` — persists to `review_learnings` table.
   - **Lines 1105-1120:** **Emission**: `emit_artifact(...artifact_type="learned_rules"...)` — fires learned rules as a seed for downstream consumers.

4. **Next action determination:** `src/buildlog/core/operations.py:3030-3054`:
   - Criticals exist → `"fix_criticals"` (auto-fix loop).
   - Majors exist → `"checkpoint_majors"` (ask user).
   - Minors exist → `"checkpoint_minors"` (ask user to accept risk).
   - Nothing → `"clean"` (all clear, proceed).

### What the user sees

```json
{
  "action": "fix_criticals",
  "criticals": [{"severity": "critical", "description": "SQL injection..."}],
  "majors": [],
  "minors": [{"severity": "minor", "description": "Missing docstring..."}],
  "learnings_persisted": 3,
  "rules_credited": ["security_karen:rule:0", "test_terrorist:rule:3"],
  "message": "1 critical, 0 major, 1 minor. Fix criticals and re-review."
}
```

---

## 5. Reward & Mistake Logging

### What happens

Two feedback paths update the bandit:
- **Explicit rewards** via `buildlog_log_reward()` — the user says "accepted", "revision", or "rejected".
- **Implicit negative signals** via `buildlog_log_mistake()` — a mistake is logged during a session, teaching the bandit the active rules failed to prevent it.

### Code path: Reward logging

1. **MCP wrapper:** `src/buildlog/mcp/tools.py:279-344` — `buildlog_log_reward()`.

2. **Core function:** `src/buildlog/core/operations.py:1185-1312` — `log_reward()`:
   - **Line 1227:** `_compute_reward_value()` — maps outcome to `[0, 1]`:
     - `"accepted"` → `1.0` (rules helped, full credit).
     - `"rejected"` → `0.0` (rules failed, zero credit).
     - `"revision"` → `1 - revision_distance` (partial credit).
   - **Lines 1229-1240:** Gets active session data (if no explicit `rules_active` or `error_class` provided).
   - **Line 1255:** `backend.append_event(project_id, "rewards", event.to_dict())` — persists to `reward_events` table (`storage/sqlite.py:294-315`).
   - **Lines 1273-1280:** **Bandit update:** `bandit.batch_update(rule_ids, reward_value, context)` — updates Beta distributions for all active rules.
   - **Lines 1288-1298:** **Emission:** `emit_artifact(...artifact_type="reward_signal"...)` — fires reward signal to `~/.buildlog/emissions/pending/`.

### Code path: Mistake logging

1. **MCP wrapper:** `src/buildlog/mcp/tools.py:470-523` — `buildlog_log_mistake()`.

2. **Core function:** `src/buildlog/core/operations.py:2491-2650` — `log_mistake()`:
   - **Line 2571:** `_generate_mistake_id()` — unique ID from `error_class + timestamp`.
   - **Lines 2573-2578:** `_find_similar_prior_mistake()` — checks for repeat patterns across sessions.
   - **Line 2597:** `backend.append_event(project_id, "mistakes", mistake.to_dict())` — persists to `mistakes` table.
   - **Lines 2599-2650:** **Bandit learning (implicit negative feedback)**:
     - Gets the session's `selected_rules`.
     - For each: `bandit.batch_update(selected_rules, reward=0.0, context=error_class)`.
     - This teaches the bandit: "these rules were active but a mistake still happened. They didn't prevent it."

---

## 6. Bandit Update (The Bayesian Core)

### What happens

Every reward and mistake updates a Beta distribution for each affected rule. This is the mathematical core of the learning loop.

### Code path

1. **Single update:** `src/buildlog/core/bandit.py:671-730` — `update()`:
   - **Lines 697-703:** Get or initialize the rule's `BetaParams(alpha, beta)`.
   - **Line 706:** `params.update(reward)` — the Beta update rule:
     - `alpha_new = alpha + reward`
     - `beta_new = beta + (1 - reward)`
     - If `reward = 1.0`: alpha increases → distribution shifts right (higher mean).
     - If `reward = 0.0`: beta increases → distribution shifts left (lower mean).
     - If `0 < reward < 1`: both increase → distribution narrows (more confidence, less exploration).
   - **Line 709:** `self._persistence.append_update()` — append-only write for crash safety.

2. **Batch update:** `src/buildlog/core/bandit.py:711` — `batch_update()`:
   - Calls `update()` for each rule in the list.

3. **BetaParams:** `src/buildlog/core/bandit.py:111-150`:
   - `alpha: float` and `beta: float` — pseudo-counts.
   - **Mean:** `alpha / (alpha + beta)` — the expected success rate.
   - **Variance:** `alpha * beta / ((alpha + beta)^2 * (alpha + beta + 1))` — uncertainty measure.
   - **Confidence interval:** 5th and 95th percentiles of the Beta distribution.

### What matters

Thompson Sampling doesn't just track "which rules are good." It tracks **how confident we are** about each rule. A rule with `Beta(2, 1)` (mean 0.67, high variance) will occasionally sample very high values, so the bandit explores it. A rule with `Beta(20, 10)` (mean 0.67, low variance) samples near its mean, so the bandit exploits it. Exploration decays naturally as evidence accumulates.

---

## 7. Skill Promotion & Rule Unification

### What happens

Journal entries get distilled into patterns, patterns become skills, skills get promoted to gauntlet rules. After PR #190, promoted skills are inserted directly into the `gauntlet_rules` table with `persona = "learned"`, so `_get_current_rules()` returns them alongside seed rules.

### Code path

1. **Distill:** `src/buildlog/distill.py` — `distill_all(buildlog_dir)` parses all entries, extracts improvement patterns by category (`architectural`, `workflow`, `tool_usage`, `domain_knowledge`).

2. **Generate skills:** `src/buildlog/skills.py:465-600` — `generate_skills()`:
   - **Line 502:** Calls `distill_all()` for raw patterns.
   - **Lines 517-522:** Deduplicates via embedding similarity.
   - **Line 560:** `_generate_skill_id(category, rule)` — deterministic ID (`skills.py:217-233`):
     - Category prefix: `arch`, `wf`, `tool`, `dk`, `sk` (line 224-230).
     - Hash: `hashlib.sha256(rule.lower()).hexdigest()[:10]` (line 232).
     - Result: e.g., `arch-a1b2c3d4ef`.

3. **Promote:** `src/buildlog/core/operations.py:625-742` — `promote()`:
   - **Line 659:** `generate_skills(buildlog_dir)` — gets all skills.
   - **Line 675:** `get_renderer(target)` — gets output renderer (CLAUDE.md, Cursor, Copilot, etc.).
   - **Line 677:** `renderer.render(found_skills)` — writes rules to the target file.
   - **Lines 681-685:** `backend.save_id_set(..., "promoted", ...)` — persists promoted IDs.
   - **Lines 687-734:** **Rule unification (PR #190):**
     - For each skill, creates a gauntlet_rules row with `persona = "learned"` (line 712).
     - Includes provenance JSON with confidence, frequency, sources.
     - **Line 726-730:** `backend.save_gauntlet_rules_batch()` — batch upsert into `gauntlet_rules` table.

4. **Batch upsert:** `src/buildlog/storage/sqlite.py:539-591` — `save_gauntlet_rules_batch()`:
   - **Lines 548-570:** `INSERT INTO gauntlet_rules ... ON CONFLICT(rule_id) DO UPDATE` — upserts each rule.
   - **Line 591:** `self.conn.commit()` — atomic batch commit.

### The unification

After this, `_get_current_rules()` (`operations.py:1907-1928`) returns seeds AND promoted skills in a single list. The bandit treats them identically. They compete on equal footing in Thompson Sampling.

---

## 8. Emission Pipeline (Fire-and-Forget)

### What happens

Every `log_reward()`, `log_mistake()`, and `learn_from_review()` fires a structured JSON artifact to `~/.buildlog/emissions/pending/`. These artifacts are consumed into the local edge store and, separately, ingested by qortex into Memgraph.

### Code path: Emitting

1. **Emit function:** `src/buildlog/emissions/__init__.py:81-120` — `emit_artifact()`:
   - Writes to `~/.buildlog/emissions/pending/{type}_{project}_{timestamp}.json`.
   - Appends a signal log entry to `~/.buildlog/emissions/signal.jsonl` (line 105).
   - Fire-and-forget: failures are silently swallowed. Emissions never block the primary loop.

2. **Artifact types emitted:**
   - `reward_signal` — from `log_reward()` (`operations.py:1292`).
   - `mistake_manifest` — from `log_mistake()` (with concepts and edges).
   - `learned_rules` — from `learn_from_review()` (`operations.py:1112-1116`).
   - `session_summary` — from `end_session()` (with duration, mistakes, rule delta).

### Code path: Consuming (local)

1. **Consumer:** `src/buildlog/emissions/consumer.py:81-180` — `consume_pending_emissions()`:
   - **Lines 104-106:** Scans `~/.buildlog/emissions/pending/` for JSON files.
   - **Line 132:** `_classify_artifact_type(filename)` — determines type from filename prefix.
   - **Lines 142-146:** If the artifact type has edges: `_extract_edges()` → `backend.store_emission_edges()`.
   - **Lines 149-150:** Moves artifact to `processed/` directory.
   - **Lines 167-178:** On error: moves to `failed/` with `.error` sidecar file.

2. **Edge extraction:** `src/buildlog/emissions/consumer.py:54-78` — `_extract_edges()`:
   - For each edge in the artifact: extracts `source_id`, `target_id`, `relation_type`, `confidence`.
   - Enriches with `artifact_type`, `project_id`, `emitted_at`, `consumed_at`.

### What accumulates

```
~/.buildlog/emissions/
  pending/       ← unprocessed artifacts
  processed/     ← consumed artifacts
  failed/        ← artifacts that errored during consumption
  signal.jsonl   ← append-only log of all emission events
```

---

## 9. Marimo Dashboard (What You See)

### Location

`notebooks/dashboard.py` — run with `uv run marimo run notebooks/dashboard.py --port 2718`.

### Tab 1: Overview (lines 144-304)

**Data source:** `src/buildlog/stats.py:303` — `calculate_stats()` and `backend.load_events(project_id, "rewards")`.

**What you see:**
- **4 KPI cards:** Total entries, current streak, coverage %, this week count.
- **Reward Trend chart:** Running mean of reward values over time (line 208-254). A line chart with fill-to-zero. Two dashed reference lines: green at 0.7 (target) and red at 0.4 (investigate). **A healthy system shows the line above 0.7.** If it dips below 0.4, the review process needs attention.
- **Outcome Distribution donut:** Proportions of accepted/revision/rejected outcomes (lines 264-289). **A healthy system is mostly green (accepted).**

### Tab 2: Sessions & Mistakes (lines 307-513)

**Data source:** `backend.load_events(project_id, "sessions")` and `backend.load_events(project_id, "mistakes")`.

**What you see:**
- **Rule Growth bar chart:** Grouped bars showing `rules_at_start` vs `rules_at_end` for each session (lines 356-387). **If end > start, the session discovered new rules.** Monotonic growth = the system is learning.
- **Mistake KPIs:** Total mistakes, repeat rate %, unique error classes (lines 416-428).
- **Mistakes by Error Class:** Horizontal bar chart showing which error classes occur most (lines 434-452). **Tall bars = recurring problems the system hasn't solved yet.**
- **Repeated Mistake Rate (RMR):** Line chart tracking the percentage of mistakes per session that were previously seen (lines 466-489). **This should trend downward.** A rising RMR means rules aren't preventing known mistakes.

### Tab 3: Bandit & Rules (lines 516-703)

**Data source:** `src/buildlog/core/learning.py` — `get_learning_backend(buildlog_dir).get_stats(None)`.

**What you see:**
- **Thompson Sampling Posteriors:** Horizontal bar chart of posterior means with 90% credible interval error bars (lines 584-633).
  - **Green bars (mean >= 0.7):** High-confidence winners. The bandit will reliably select these.
  - **Red bars (mean < 0.4):** Weak rules. Candidates for revision or retirement.
  - **Blue bars:** Uncertain, need more observations.
  - **Wide error bars:** High uncertainty. The bandit is still exploring.
  - **Narrow error bars:** High confidence. The bandit is exploiting.
  - **`n=X` labels:** Number of observations. Low n = unreliable estimate.
- **Rule Selection Frequency:** How often the bandit picks each rule across sessions (lines 660-687). **Popular rules with low posterior means = rules the bandit explored and found wanting.**

### Tab 4: Emissions (lines 706-949)

**Data source:** `~/.buildlog/emissions/signal.jsonl` and `backend.load_emission_edges()`.

**What you see:**
- **Pipeline KPIs:** Emitted count, consumed count, pending count, edge count (lines 781-795). **Pending should be 0** in a healthy pipeline. Non-zero = run `buildlog_consume_emissions()`.
- **Emission Rate Over Time:** Stacked area chart showing daily emission volume by artifact type (lines 812-849). Red = mistakes, green = rewards, purple = learned rules, cyan = sessions. **Dotted amber overlay shows consumption rate.** When consumed matches emitted, the pipeline is keeping up.
- **Artifacts by Type:** Bar chart of total artifact counts by type (lines 871-889).
- **Edge Types donut:** Distribution of relationship types in stored edges (lines 900-929). Shows CONTAINS, BELONGS_TO, USES proportions.

### Tab 5: Insights & Health (lines 952-1119)

**Data source:** `stats.insights`, `backend.conn.execute("SELECT ... FROM review_learnings ...")`.

**What you see:**
- **Insights by Category:** Horizontal bars showing pattern counts from `buildlog distill` (lines 999-1022).
- **Review Learnings chart:** Grouped horizontal bars — green (reinforced) vs red (contradicted) for each learning (lines 1039-1073). **High green with zero red = strong signal.** Red bars = rules that were later proven wrong.
- **System Health:** Top source entries and quality warnings (lines 1087-1108).

---

## 10. qortex Ingestion into Memgraph

### What happens

`qortex ingest emissions` reads the same `~/.buildlog/emissions/` directory, aggregates all artifacts into concepts and edges, bridges gauntlet rules as cross-domain nodes, and loads everything into Memgraph via Cypher queries.

At this step, buildlog's data **leaves the buildlog silo**. buildlog knows about sessions, mistakes, and rules, but it has no concept of how those rules relate to design patterns, other projects, or each other beyond their bandit statistics. qortex bridges that gap.

### Code path

1. **CLI command:** `src/qortex/cli/ingest.py:357-548` — `ingest_emissions()`:
   - **Lines 432-436:** `aggregate_emissions(emissions_dir, include_pending, include_processed)` — reads all JSON artifacts.
   - **Lines 450-454:** `resolve_historical_targets(result, db_path)` — resolves bare skill IDs (e.g., `arch-b0fcb62a1e`) to `gauntlet_rule:{rule_id}` format.
   - **Line 460:** `build_manifest(result, domain)` — creates `IngestionManifest`.
   - **Lines 462-471:** `bridge_gauntlet_rules(db_path)` — reads gauntlet rules from buildlog DB, creates cross-domain concept nodes.

2. **Aggregation engine:** `src/qortex/ingest_emissions.py:235-315` — `aggregate_emissions()`:
   - **Lines 258-313:** For each JSON artifact:
     - **Line 263:** `_classify_artifact(filename)` — determines type.
     - **Lines 280-283:** Extracts concepts via `_extract_concept()` (line 78-118):
       - `mistake_manifest` → description: `"Mistake ({error_class}) — {description}"`.
       - `reward_signal` → description: `"Reward: {outcome} (value={reward_value})"`.
       - `session_summary` → description: `"Session: {duration}min, {mistakes} mistakes"`.
     - **Lines 285-313:** Extracts edges with deduplication via `seen_edge_pairs` set.
     - **Lines 297-305:** Creates stub concepts for edge endpoints that don't exist yet.

3. **Cross-domain bridging:** `src/qortex/ingest_emissions.py:355-490` — `bridge_gauntlet_rules()`:
   - **Line 379-381:** Queries `gauntlet_rules` table from buildlog DB.
   - **Lines 407-442:** For experiential rules (no design-pattern domain):
     - Creates `persona:{name}` concept nodes.
     - Creates `gauntlet_rule:{rule_id}` concept nodes.
     - Creates `BELONGS_TO` edges linking rules to personas.
   - **Lines 445-487:** For rules WITH a design-pattern domain (cross-domain bridge):
     - Creates concept nodes IN the source domain (e.g., `observer_pattern`).
     - Creates `INSTANCE_OF` edges linking rules to their domain anchors.

4. **Memgraph loading:** `src/qortex/core/backend.py:695-737` — `ingest_manifest()`:
   - **Line 711:** `create_domain(manifest.domain)` — creates Domain node via Cypher: `MERGE (d:Domain {name: $name})` (line 426-430).
   - **Lines 720-721:** For each concept: `add_node(node)` — creates Concept node via Cypher: `MERGE (c:Concept {id: $id}) SET c.name = $name, c.domain = $domain...` (line 507-521).
   - **Lines 722-723:** For each edge: `add_edge(edge)` — creates relationship via Cypher: `MATCH (s:Concept {id: $src}), (t:Concept {id: $tgt}) CREATE (s)-[:{RELATION_TYPE}]->(t)` (line 589-592). The relation type becomes the actual Cypher edge label (CONTAINS, BELONGS_TO, USES, etc.).
   - **Lines 724-725:** For each rule: `add_rule(rule)` — creates Rule node via Cypher: `MERGE (r:Rule {id: $id}) SET r.text = $text, r.domain = $domain...` (line 653-657).

### CLI reference

```bash
# Full pipeline — ingest all emissions into Memgraph with cross-domain bridging
qortex ingest emissions

# Dry run — show stats without writing to Memgraph
qortex ingest emissions --dry-run

# Save the aggregated manifest to inspect offline
qortex ingest emissions -o emissions_manifest.json

# Skip cross-domain bridging (buildlog data only, no pattern linking)
qortex ingest emissions --no-bridge

# Ingest only pending artifacts (not yet consumed by buildlog)
qortex ingest emissions --no-processed

# Custom emissions directory and DB path
qortex ingest emissions --dir ~/.buildlog/emissions --db ~/.buildlog/buildlog.db

# Inspect what's in Memgraph after ingestion
qortex inspect stats      # → Domains: 12, Concepts: 2749, Edges: 9381, Rules: 76
qortex inspect domains    # → domain-by-domain breakdown
qortex inspect rules      # → all rules with domains and provenance

# Query Memgraph directly via Cypher
qortex viz query "MATCH (n:Concept {domain: 'buildlog'}) RETURN count(n)"

# Seed projections (see what qortex would export back to buildlog)
qortex project seeds --domain buildlog --no-edges
```

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--dir / -d` | `~/.buildlog/emissions` | Root emissions directory |
| `--domain` | `buildlog` | Domain name for ingested data |
| `--pending / --no-pending` | `--pending` | Include `pending/` artifacts |
| `--processed / --no-processed` | `--processed` | Include `processed/` artifacts |
| `--dry-run` | off | Show aggregation stats without loading into Memgraph |
| `--save-manifest / -o` | none | Path to save manifest as JSON |
| `--bridge / --no-bridge` | `--bridge` | Bridge gauntlet rules to design pattern domains |
| `--db` | `~/.buildlog/buildlog.db` | Path to buildlog SQLite database |
| `--resolve-rules / --no-resolve-rules` | `--resolve-rules` | Resolve historical skill IDs to `gauntlet_rule:{id}` format |

---

## 11. Cross-Domain Discovery & Rule Re-Export

### What happens

qortex does what buildlog **cannot**: discover relationships across domain boundaries.

buildlog operates in a single domain. It knows that `security_karen:rule:0` was selected in session X, that a mistake happened, and that the bandit penalized it. It has no concept of how that rule relates to `observer_pattern` or `implementation_hiding` or any other design pattern domain. The domains are **separate silos**: buildlog's gauntlet rules, MindMirror's insight categories, interlinear's vocabulary patterns. Each system generates data independently. None of them can see each other.

qortex can. By ingesting emissions from multiple systems into the same knowledge graph, qortex sees the **topology that no individual system has access to**. A gauntlet rule about "decouple publishers from subscribers" that was learned in buildlog gets placed into the `observer_pattern` domain via `bridge_gauntlet_rules()`. Now that rule is connected to observer pattern concepts that came from a completely different source (curated design pattern knowledge). qortex can traverse from a buildlog session, to a mistake, to a rule, to a design pattern, to other rules in other projects that are instances of the same pattern.

### How cross-domain bridging works

1. **Rule classification by provenance** (`src/qortex/ingest_emissions.py:389-443`):
   - Each gauntlet rule has a `provenance` JSON field.
   - Rules whose provenance includes a `domain` key (e.g., `"observer_pattern"`, `"factory_patterns"`, `"implementation_hiding"`) are **bridge candidates**.
   - Rules without a domain stay in the `buildlog` domain as persona-linked concepts.

2. **Bridge creation** (`src/qortex/ingest_emissions.py:445-487`):
   - Bridge rules are created as concept nodes **in the target domain** (not `buildlog`).
   - They get a `bridge: True` property marking them as cross-domain connectors.
   - An `INSTANCE_OF` edge connects the rule to its domain anchor:
     ```
     gauntlet_rule:security_karen:rule:42 --INSTANCE_OF--> domain:observer_pattern
     ```
   - This single edge is what enables cross-domain traversal.

3. **What this unlocks:**
   ```
   buildlog session → CONTAINS → mistake
                    → USES → gauntlet_rule:rule_42
                                ↓ INSTANCE_OF
                          observer_pattern (domain)
                                ↑ INSTANCE_OF
                      gauntlet_rule:rule_99 (from interlinear)
                                ↓ USES
                          interlinear session
   ```
   qortex can now answer: "Which mistakes in buildlog are structurally related to problems in interlinear?" Neither system could answer that alone.

### Rule re-export: the projection pipeline

qortex doesn't just discover cross-domain relationships. It **projects new rules back** to the source systems.

**Architecture** (`src/qortex/projectors/`):

```
ProjectionSource (derives rules from KG)
       ↓
   Enricher (adds context/antipattern/rationale)
       ↓
ProjectionTarget (serializes to consumer format)
```

1. **Source** (`src/qortex/projectors/sources/flat.py:33-52`):
   - `FlatRuleSource.derive()` extracts rules from the graph via two strategies:
     - **Explicit rules:** Rules directly stored as Rule nodes.
     - **Derived rules:** Generated from edges using a template registry. For example, an `INSTANCE_OF` edge between a mistake and a pattern domain can generate: "Mistakes of type X are instances of pattern Y. Consider applying Y's mitigations."
   - Deduplicates by `(source_id, target_id)` pair (`flat.py:108-112`).

2. **Enricher** (optional):
   - Adds `context`, `antipattern`, `rationale` fields to bare rules.
   - Can use LLM-backed enrichment or rule templates.

3. **Target** (`src/qortex/projectors/targets/buildlog_seed.py`):
   - `BuildlogSeedTarget` serializes rules into buildlog's seed format.
   - Output is compatible with `buildlog.SeedFile.from_dict()`.
   - Each projected rule carries provenance tracking its graph origin:
     ```json
     {
       "rule": "Decouple publishers from subscribers at module boundaries",
       "category": "architectural",
       "provenance": {
         "id": "gauntlet_rule:obs-001",
         "domain": "observer_pattern",
         "derivation": "explicit",
         "confidence": 0.95,
         "graph_version": "2026-02-14T16:51:49Z"
       }
     }
     ```

4. **Serialization** (`src/qortex/projectors/targets/_serialize.py:113-156`):
   - `serialize_ruleset()` produces a universal schema with persona, version, rules array, and metadata.
   - The `source: "qortex"` field marks these as graph-derived rules, distinguishing them from manually authored seeds.

### The re-export loop

```
buildlog emits → qortex ingests → graph discovers cross-domain patterns
     ↑                                          ↓
     └── qortex projects new rules ←── Projection pipeline
```

Rules that qortex discovers through cross-domain traversal get projected back as new seed files. These seeds flow into buildlog's gauntlet, compete in Thompson Sampling alongside hand-written rules, and get measured the same way. **The system can discover rules that no human wrote**, derived purely from the topology of the knowledge graph.

### CLI commands for projection

```bash
# Project rules from the observer_pattern domain as buildlog seeds
qortex project seeds --domain observer_pattern

# Project without derived edges (explicit rules only)
qortex project seeds --domain buildlog --no-edges

# Dry-run: inspect what would be projected
qortex project seeds --domain observer_pattern --dry-run
```

---

## 12. Memgraph Visualization (What You See)

### Access

- **Memgraph Lab:** http://localhost:3000 — visual graph explorer with query editor.
- **CLI:** `uv run qortex viz query "MATCH ..."` — run Cypher from terminal (`src/qortex/cli/viz.py:25-47`).
- **Inspect commands:** `uv run qortex inspect domains|rules|stats` (`src/qortex/cli/inspect_cmd.py`).

### What's in the graph (as of 2026-02-14)

```
Domains:   12
Concepts:  2,749
Edges:     9,381
Rules:     76
```

The `buildlog` domain contains:
- **305 session nodes** — each a `Concept` with `name = "session:session-YYYYMMDD-..."`.
- **75 rule/other nodes** — gauntlet rules and personas.
- **65 mistake nodes** — each a `Concept` with `name = "mistake:mistake-{error_class}-..."`.
- **3,021 edges:** 347 CONTAINS, 165 BELONGS_TO, 38 USES.

### What each query shows

**Graph overview:**
```cypher
-- Node types in buildlog domain
MATCH (n:Concept {domain: 'buildlog'})
RETURN CASE
  WHEN n.name STARTS WITH 'session:' THEN 'session'
  WHEN n.name STARTS WITH 'mistake:' THEN 'mistake'
  WHEN n.name STARTS WITH 'reward:' THEN 'reward'
  ELSE 'rule/other'
END AS type, count(*) AS cnt ORDER BY cnt DESC
```
Shows: 305 sessions, 75 rules, 65 mistakes.

**Session → Mistake containment:**
```cypher
-- Which sessions had which mistakes
MATCH (s:Concept {domain: 'buildlog'})-[:CONTAINS]->(m:Concept)
WHERE m.name STARTS WITH 'mistake:'
RETURN s.name AS session, m.name AS mistake LIMIT 15
```
Shows: `session:session-20260214-122536-865790` CONTAINS `mistake:mistake-missing_te-20260214-122536-893206`. This is the "a mistake happened during this session" relationship.

**Session → Rule usage:**
```cypher
-- Which rules were active in which sessions
MATCH (s:Concept {domain: 'buildlog'})-[:USES]->(r:Concept)
RETURN s.name AS session, r.name AS rule LIMIT 15
```
Shows: `session:session-20260214-122116-225805` USES `r1`, `r2`. This is "the bandit selected these rules for this session."

**Edge type distribution:**
```cypher
-- What kinds of relationships exist
MATCH (a:Concept {domain: 'buildlog'})-[r]->(b:Concept)
RETURN type(r) AS rel, count(*) AS cnt ORDER BY cnt DESC
```
Shows: CONTAINS (347), BELONGS_TO (165), USES (38).

**Cross-domain view:**
```cypher
-- All 12 domains
MATCH (n:Concept)
RETURN n.domain AS domain, count(*) AS cnt ORDER BY cnt DESC
```
Shows buildlog alongside design-pattern domains (observer_pattern, factory_patterns, etc.). The gauntlet rule bridging connects experiential learning data to curated design knowledge.

**In Memgraph Lab** (http://localhost:3000), you can visualize these as interactive graphs. Drag nodes, zoom, and see the web of relationships between sessions, mistakes, and rules.

---

## 13. The Loop Closes

Here is the complete cycle, traced through code:

```
User installs buildlog
  └─ cli.py:61 init() → registers MCP server (mcp/server.py:44)

Agent starts session
  └─ operations.py:2072 start_session()
     └─ operations.py:1907 _get_current_rules() → union of seeds + promoted
     └─ bandit.py:606 select() → Thompson Sampling picks top-k rules
        └─ bandit.py:659 params.sample() → sample from Beta distribution

Agent reviews code with gauntlet
  └─ operations.py:4060 gauntlet_loop_config() → generates prompt with rules

Agent reports issues
  └─ operations.py:2924 gauntlet_process_issues()
     └─ operations.py:997 learn_from_review() → persists ReviewLearnings
        └─ emissions/__init__.py:81 emit_artifact("learned_rules")
     └─ bandit.py:671 update(rule, reward=1.0) → credit cited rules

Agent logs mistakes
  └─ operations.py:2491 log_mistake()
     └─ bandit.py:711 batch_update(rules, reward=0.0) → penalize active rules

User provides feedback
  └─ operations.py:1185 log_reward()
     └─ bandit.py:711 batch_update(rules, reward) → update all active rules
     └─ emissions/__init__.py:81 emit_artifact("reward_signal")

Bandit distributions update
  └─ bandit.py:706 params.update(reward) → Beta(α+r, β+(1-r))
     └─ Next session: better rules selected, worse rules deprioritized

Skills extracted from journal
  └─ skills.py:465 generate_skills() → distill patterns into Skill objects
     └─ skills.py:217 _generate_skill_id() → deterministic hash ID

Skills promoted to gauntlet
  └─ operations.py:625 promote()
     └─ operations.py:687-734 → INSERT into gauntlet_rules with persona="learned"
     └─ Now appears in _get_current_rules() alongside seeds

Emissions flow to qortex
  └─ ~/.buildlog/emissions/pending/ → JSON artifacts
     └─ qortex/ingest_emissions.py:235 aggregate_emissions()
     └─ qortex/ingest_emissions.py:355 bridge_gauntlet_rules()
        └─ Classifies rules by provenance domain
        └─ Creates INSTANCE_OF edges to design pattern domains
     └─ qortex/core/backend.py:695 ingest_manifest()
        └─ MERGE (c:Concept ...) → Memgraph nodes
        └─ CREATE (s)-[:CONTAINS]->(t) → Memgraph edges

qortex discovers cross-domain relationships
  └─ Graph traversal across domain boundaries
     └─ buildlog rule → INSTANCE_OF → observer_pattern domain
     └─ interlinear rule → INSTANCE_OF → observer_pattern domain
     └─ Neither system could see this connection alone

qortex projects new rules back
  └─ projectors/sources/flat.py:33 FlatRuleSource.derive()
     └─ Explicit rules + derived rules from edge templates
  └─ projectors/targets/buildlog_seed.py → BuildlogSeedTarget
     └─ Serialized as buildlog seed files with provenance
  └─ New rules enter buildlog's gauntlet → compete in Thompson Sampling

Visualized in Marimo
  └─ notebooks/dashboard.py → 5 tabs showing reward trends,
     RMR, bandit posteriors, emission pipeline health

Visualized in Memgraph
  └─ qortex viz query "..." → Cypher queries over the knowledge graph
  └─ http://localhost:3000 → Memgraph Lab visual explorer

THE LOOP CLOSES: better rules → fewer mistakes → higher rewards
  → bandit concentrates on winning rules → system improves
  → qortex discovers cross-domain patterns → projects new rules
  → new rules compete alongside hand-written seeds
  → the system discovers rules no human wrote
```

---

## Verification

All of the above can be verified right now:

```bash
# 1. Dashboard is live
open http://localhost:2718

# 2. Memgraph has data
cd /Users/peleke/Documents/Projects/qortex
uv run qortex inspect stats
# → Domains: 12, Concepts: 2749, Edges: 9381, Rules: 76

# 3. Learning loop verification passes 10/10
cd /Users/peleke/Documents/Projects/buildlog-template
uv run python scripts/verify_learning_loop_live.py

# 4. Memgraph Lab is accessible
open http://localhost:3000
```
