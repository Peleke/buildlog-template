# Hello World

This walkthrough takes you from zero to a promoted rule in a real project. The commands and outputs below reflect a typical first run. By the end, you'll have buildlog extracting patterns from your work and writing rules into your agent's instruction file. It takes about 15 minutes.

## Prerequisites

- Python 3.11+
- A git repository (any project works)
- Claude Code installed (for MCP integration)

## Step 1: Install and register

```bash
pipx install buildlog
buildlog init-mcp --global -y
```

Verify:

```bash
buildlog mcp-test
```

```
Found 36 tools:
  buildlog_status
  buildlog_promote
  buildlog_reject
  buildlog_diff
  ...
All 36 tools registered. OK.
```

## Step 2: Initialize in your project

```bash
cd ~/my-project
buildlog init --defaults
```

```
Created buildlog/ directory with templates
Registered MCP server in .claude/settings.json
Updated CLAUDE.md with buildlog integration section
```

This creates:

```
my-project/
├── buildlog/
│   ├── .buildlog/        # internal state (don't edit)
│   └── TEMPLATE.md       # entry template
├── CLAUDE.md             # updated with buildlog instructions
└── ...your code...
```

## Step 3: Create your first entry

```bash
buildlog new hello-world
```

```
Created: buildlog/2026-02-13-hello-world.md
```

Open `buildlog/2026-02-13-hello-world.md` and fill it in. The template has sections for what you did, what went wrong, and what you learned. The "Improvements" section is what the extraction pipeline reads. Write something concrete:

```markdown
# 2026-02-13 Hello World

## Context
Setting up buildlog for the first time in this project.

## What Happened
Initialized buildlog, created first entry, ran through the pipeline.

## Mistakes
- Forgot to run `buildlog init` before trying to create an entry.
  Error message was clear, but I should have read the docs first.

## Improvements
- **architectural**: Always initialize tooling before using it. Run `buildlog init --defaults` in every new project before creating entries.
- **workflow**: Create a buildlog entry at the start of each work session, not at the end. Capture decisions while they're fresh.
```

The format matters: `- **category**: Rule text.` is what the extractor looks for. Valid categories: `architectural`, `workflow`, `tool_usage`, `domain_knowledge`.

## Step 4: Extract patterns

```bash
buildlog distill
```

```
Extracted at: 2026-02-13T14:30:00
Entries processed: 1
Patterns found: 2
  architectural: 1
  workflow: 1
```

This parses the Improvements section and pulls out structured patterns. With one entry you'll get raw patterns. With many entries, the system deduplicates and tracks frequency.

## Step 5: Generate skills

```bash
buildlog skills
```

```
Generated at: 2026-02-13T14:30:15
Source entries: 1
Total skills: 2

architectural:
  arch-a1b2c3d4e5  Always initialize tooling before using it  (freq: 1, confidence: low)

workflow:
  wf-f6g7h8i9j0  Create a buildlog entry at the start of each work session  (freq: 1, confidence: low)
```

Each skill gets a stable ID (e.g., `arch-a1b2c3d4e5`) based on its category and rule text. The ID is deterministic. The same input always produces the same ID.

## Step 6: Check what's pending

```bash
buildlog status
```

```
Skills by category:
  architectural: 1 skill
  workflow: 1 skill

Total: 2 skills (0 promoted, 0 rejected)
```

```bash
buildlog diff
```

```
Pending skills (not yet promoted or rejected):

  arch-a1b2c3d4e5  Always initialize tooling before using it
  wf-f6g7h8i9j0    Create a buildlog entry at the start of each work session
```

## Step 7: Promote a rule

Promoting writes the rule into the file your agent reads.

```bash
buildlog promote arch-a1b2c3d4e5 wf-f6g7h8i9j0 --target claude_md
```

```
Promoted 2 skills to CLAUDE.md:
  arch-a1b2c3d4e5  Always initialize tooling before using it
  wf-f6g7h8i9j0    Create a buildlog entry at the start of each work session
```

Open your `CLAUDE.md`. You'll see a new section:

```markdown
<!-- buildlog:rules:start -->

## Learned Rules (buildlog, updated 2026-02-13)

### Architectural

- Always initialize tooling before using it

### Workflow

- Create a buildlog entry at the start of each work session

<!-- buildlog:rules:end -->
```

Claude Code reads this file at session start. Your agent now has rules derived from your project history.

## Step 8: Close the loop with the gauntlet

The gauntlet is the primary feedback mechanism. It runs curated reviewer personas against your code and credits rules that reviewers cite.

```bash
buildlog gauntlet-loop --target src/
```

The gauntlet finds issues, you fix them, and re-run until clean. Each credited rule citation updates the Thompson Sampling posteriors.

After your work is reviewed and accepted:

```bash
buildlog log-reward --outcome accepted
```

The `accepted` outcome shifts the bandit posteriors. Rules that were cited during gauntlet reviews get credit. Over time, the system converges on the rules that actually reduce mistakes in your codebase.

For optional longitudinal RMR tracking across sessions, see the [Experiments guide](../guides/experiments.md).

You now have a working pipeline from journal entry to promoted rule, with gauntlet review closing the feedback loop.

## Next steps

- **Run the gauntlet**: `buildlog gauntlet-loop --target src/` runs curated reviewer personas against your code and extracts rules from the findings
- **Add more entries**: The system gets better with more data. Document mistakes, since they produce the most actionable rules.
- **Check the bandit**: `buildlog bandit-status` shows which rules the system thinks are effective and how confident it is
- **Read [Core Concepts](concepts.md)** for the theory behind RMR and Thompson Sampling
- **Read [MCP Integration](../guides/mcp-integration.md)** if you want Claude to run the loop automatically
