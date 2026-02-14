# buildlog Development Guidelines

## Standard Development Workflow

Every feature/fix follows this loop. No exceptions.

### 1. Issue + Branch
```
gh issue create --title "feat: ..." --body "..."
git checkout -b feat/<slug>
```

### 2. Implement with Commits + Entries
After every substantial change (something that ticks off a todo item):
```
git add <files>
buildlog_commit(message="feat: description of change")
buildlog_entry_new(slug="<feature-slug>")  # once per session
```

### 3. Gauntlet Review
After all implementation is done:
```
buildlog_gauntlet_loop(target="src/", personas=None)
# Follow the loop: review → fix → commit → repeat
```

### 4. PR Closing the Issue
```
gh pr create --title "..." --body "Closes #<issue>"
```

### 5. Feedback Loop
After PR merge:
```
buildlog_log_reward(outcome="accepted")
```

### Key Principles
- **NEVER commit directly to main** — always branch, PR, merge
- **Commit after every substantial change**, not just at the end
- **Every commit gets a buildlog entry** via `buildlog_commit()`
- **Gauntlet before PR** — run the review loop, fix criticals/majors
- **Close the feedback loop** — `log_reward()` after merge

<!-- buildlog:rules:start -->

## Learned Rules (buildlog, updated 2026-02-14)

### Architectural

- Always define interfaces before implementations

<!-- buildlog:rules:end -->
