# Build Journal: Session Tracking, Reward Signals, and README Manifesto

**Date:** 2026-01-21
**Duration:** 5 hours

## What I Did

Three major pieces shipped. First, the reward signal tracking system for bandit learning (#29) — this logs accept/reject/revision outcomes that feed Thompson Sampling posteriors. Second, session tracking and experiment infrastructure (#31) — start/end sessions with error class tagging and automatic duration tracking. Third, rewrote the README as a pitch-focused falsifiability manifesto (#32) with hero banners and artist CTA.

## Commits

- `cc9e8c7` feat(core): add reward signal tracking for bandit learning (#16) (#29)
- `7293921` feat(core): add session tracking and experiment infrastructure (#21) (#31)
- `0ceb6a0` docs: rewrite README as pitch-focused falsifiability manifesto (#32)
- `6400231` docs: add placeholder note, hero banners, and artist CTA
- `107cee7` docs: tweak art disclaimer wording

## What Went Wrong

The reward signal format went through two iterations before settling on the JSONL append-only log. First attempt used SQLite, which was overkill for the write-once-read-rarely pattern. Second attempt used plain JSON, which has race condition issues with concurrent appends. JSONL is the right choice: one line per event, atomic appends, easy to grep.

## What I Learned

## Improvements

### Architectural

- JSONL is the right format for append-only event logs: atomic line writes, no parse-the-whole-file overhead, trivially grep-able
- Session tracking with error class tagging enables cohort analysis: group sessions by error type to find which mistakes recur

### Workflow

- The README should be written as a manifesto, not documentation: lead with the problem and your falsifiable claim, not installation instructions
- Ship infrastructure (rewards, sessions) before the features that consume it (bandit, experiments) to avoid coupling implementation to interface

### Domain Knowledge

- Thompson Sampling needs three inputs: prior (Beta distribution params), likelihood (reward observations), and posterior updates — the reward tracking system captures the middle piece
