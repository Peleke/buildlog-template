# Build Journal: Landing Page, Docs, GH Cleanup

**Date:** 2026-02-13
**Duration:** ~3 hours (across 2 sessions)
**Status:** Complete

---

## The Goal

Ship buildlog as a product. This session covered the marketing surface (landing page), documentation polish, and GitHub hygiene — the last mile before the next engineering push (#155 rules→SQLite).

---

## What We Built

### Components

| Component | Status | Notes |
|-----------|--------|-------|
| Landing page (v4) | Working | Live at launchpad/buildlog branch, Vercel preview |
| Animated SVG diagram | Working | 6-layer architecture diagram with flow lines, pulse ring, feedback loop |
| CSS flip cards | Working | 8-component stack section, hover to reveal details |
| README update | Working | Added landing page link, version bump to v0.15 |
| GH issue cleanup | Working | Closed #53, #54, #50, #137, #138 (14→9 open issues) |
| Docs site (prior session) | Working | PRs #159-#162 merged: troubleshooting, config ref, learning backends, gauntlet guide |

---

## The Journey

### Phase 1: Landing Page v1-v3

**What we tried:**
Created a landing page on a `buildlog` branch in the launchpad repo (Vercel auto-deploys branches). Iterated through 3 versions based on feedback.

**What happened:**
- v1: Too casual, used `pipx` only
- v2: Added `uv`, more serious tone, but still too fluffy
- v3: TensorZero.com-inspired rewrite — serious, technical, both `uv` and `pipx`, 70/30 technical/marketing split

**Lesson:**
- **workflow**: Study reference sites before writing marketing copy. TensorZero's tone was the right north star from the start.

### Phase 2: Landing Page v4 — SVG Diagram + Flip Cards

**What we tried:**
Used the inline-svg-architecture-diagrams skill patterns to build an animated 6-layer diagram: Capture → Extract → Rules → Thompson Sampling → Render → Measure. Added CSS flip cards for the stack section.

**What happened:**
Git checkout conflict when switching branches (untracked `index.html` on main would be overwritten). Background task failed silently — the v3 content got committed instead of v4.

```
error: The following untracked working tree files would be overwritten by checkout: index.html
```

**The fix:**
Used Write tool to directly write the v4 content to the file on the buildlog branch, bypassing the `cp` alias issue.

**Lesson:**
- **tool_usage**: Shell aliases can silently break `cp -f`. Use the Write tool for file overwrites in agent workflows — it's deterministic and has no interactive prompts.
- **workflow**: Always verify the commit content after background git operations. A "clean" status doesn't mean the right version was committed.

### Phase 3: GH Cleanup

**What we tried:**
Closed stale issues: #137 (already closed), #138 (closed by PR), #50, #53, #54 (superseded).

**What happened:**
First background agent was killed by user, but had already closed most issues. Second agent confirmed and cleaned up the rest. Went from 14 to 9 open issues.

**Lesson:**
- **workflow**: Background agents for GH cleanup are effective but check idempotency — killing mid-run is fine if the operations are atomic (individual issue closes).

### Phase 4: Docs Site (Prior Session)

PRs #159-#162 merged to main:
- #159: Troubleshooting guide (gauntlet review, citation validation, Thompson Sampling, storage)
- #160: Config reference (env vars, config files, directory layout, seed format, extras)
- #161: Learning backends guide (builtin vs qortex, decision tree, behavioral differences)
- #162: Various doc fixes from Bragi review

---

## What's Left

- [ ] #155: Rules → SQLite (planned, needs Mary/John/Winston persona review)
- [ ] Cut new release after #155
- [ ] Landing page hero image (ComfyUI or manual)
- [ ] Landing page: consider custom domain

---

## Improvements

### Workflow

- **workflow**: Study reference sites (e.g., TensorZero) before writing marketing copy — saves 2-3 iterations
- **workflow**: Always verify commit content after background git operations, especially cross-branch workflows
- **workflow**: Background agents for batch GH operations work well — they're atomic and idempotent

### Tool Usage

- **tool_usage**: Use Write tool instead of shell `cp` for file overwrites — avoids alias issues and interactive prompts
- **tool_usage**: The inline-svg-architecture-diagrams skill produces much better diagrams than hand-crafting SVG — use it

### Domain Knowledge

- **domain_knowledge**: Vercel preview URLs follow pattern `launchpad-git-{branch}-kwayet-fs-projects.vercel.app`
- **domain_knowledge**: CSS flip cards need `perspective` on parent, `transform-style: preserve-3d` on inner, and `backface-visibility: hidden` on both faces

---

## Files Changed

```
launchpad (buildlog branch):
└── index.html              # v4 landing page with animated SVG + flip cards

buildlog-template (main):
└── README.md               # Added landing page link, version bump

GitHub issues closed:
├── #53                     # Closed (superseded)
├── #54                     # Closed (superseded)
├── #50                     # Closed (superseded)
├── #137                    # Already closed
└── #138                    # Already closed (merged PR)
```

---

*Next entry: #155 rules→SQLite implementation with Mary/John/Winston persona-driven planning*

<!-- buildlog:improvements:start -->
## What Improved This Session

**Clean session.** No mistakes were flagged.

Session ran for 0.0 minutes. targeting `sparse_data`. with 10 rules at start → 10 at end.

> Every session that measures improvement is evidence that the learning loop works. buildlog tracks what changed, learns which rules help, and improves automatically.

### Metrics

| Metric | This Session | Prior | Trend |
|--------|-------------|-------|-------|
| Mistakes caught | 0 | 1 | ↓ |
| Repeated mistakes | 0 | 0 | → |
| Rules at start | 10 | 10 | → |
| Rules at end | 10 | 10 | → |
| Mean reward | — | 1.00 | — |

### Top Rules

| Rule | Mean | Observations | Status |
|------|------|-------------|--------|
| `arch-0cda924aeb` | 0.5000 | 0 | new |
| `arch-b0fcb62a1e` | 0.5000 | 0 | new |
| `dk-22bbd76410` | 0.5000 | 0 | new |
| `dk-37bed7291f` | 0.5000 | 0 | new |
| `dk-a019284fe7` | 0.5000 | 0 | new |
| `secu-849ee7b88f` | 0.5000 | 0 | new |
| `tool-023839bebf` | 0.5000 | 0 | new |
| `tool-288da7b6a1` | 0.5000 | 0 | new |
| `wf-5a531bf437` | 0.5000 | 0 | new |
| `wf-72075fdef8` | 0.5000 | 0 | new |

<!-- buildlog:session-summary:session-20260214-045357-474682 -->
<!-- buildlog:improvements:end -->
