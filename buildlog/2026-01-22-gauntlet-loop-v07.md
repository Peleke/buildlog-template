# Build Journal: Gauntlet Loop Mode + v0.5.0 through v0.7.0 Releases

**Date:** 2026-01-22
**Duration:** 7 hours

## What I Did

Release marathon. Shipped four releases in one day. v0.5.0 added experiment infrastructure and visual regression support. v0.6.0 introduced the review gauntlet with CLI command and seed engine (#37). v0.6.1 fixed seed file bundling in the pip package (#39). v0.7.0 added gauntlet loop mode with auto-fix and human-in-the-loop checkpoints (#41). Also improved assertion quality per Test Terrorist review.

## Commits

- `f462fba` Merge branch 'feat/test-terrorist-visual-regression'
- `f59b088` release: v0.5.0 - Experiment Infrastructure & Visual Regression
- `c7ec4d6` feat(cli): add gauntlet command for review personas (#37)
- `92cef67` release: v0.6.0 - Review Gauntlet & Seed Engine
- `6933c91` fix(packaging): bundle seed files in package for pip install (#39)
- `d3abecd` release: v0.6.1 - Fix package seeds bundling
- `2fd1b98` test: improve assertion quality per Test Terrorist review
- `aa02bd8` feat(gauntlet): add loop mode with auto-fix and HITL checkpoints (#41)
- `6ce1a0d` chore: update lockfile
- `01b0719` release: v0.7.0 - Gauntlet Loop & Release Infrastructure

## What Went Wrong

Seed files were not included in the pip package because they were not listed in the package data configuration. This broke `buildlog init` for anyone installing from PyPI. The fix was straightforward (add to package_data in pyproject.toml) but the fact that it shipped broken means the release testing was insufficient. Need to test `pip install` from a fresh venv before every release.

## What I Learned

## Improvements

### Architectural

- The gauntlet loop pattern (review -> fix -> commit -> repeat) is a natural fit for AI-assisted development: each iteration is a bounded improvement pass
- HITL checkpoints in automated loops prevent runaway fixes: the human approves or rejects each batch of changes

### Workflow

- Always test `pip install` from a clean venv before releasing to catch packaging issues like missing seed files
- Rapid release cadence (4 releases in a day) is only sustainable if each release is small and focused
- The Test Terrorist persona immediately improved assertion quality: having a dedicated reviewer persona for test quality creates accountability

### Tool Usage

- pyproject.toml package_data must explicitly include non-Python files (seeds, templates, configs) or they silently vanish from the distribution
