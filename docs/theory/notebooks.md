# Interactive Notebooks

**The hands-on course for the theory behind buildlog.**

The tutorials in this section explain the *what* and *why* — multi-armed bandits, Beta distributions, Bayesian updates, Thompson Sampling, contextual bandits. The interactive notebooks let you *play with the machinery yourself*.

These are [Marimo](https://marimo.io) notebooks: reactive Python notebooks that run in your browser. Every cell re-executes when you change an input, so you can drag sliders, tweak parameters, and watch the math respond in real time. No Jupyter kernel restarts, no stale state.

---

## Available Notebooks

### 0. On Learning What Works

**File:** `notebooks/00-the-problem.py`

The explore-exploit tradeoff, from first principles. Why do agents need to balance trying new things against sticking with what works? This notebook lets you simulate the tension directly — pull slot machine arms, watch regret accumulate, and build intuition for why naive strategies fail.

Covers the same ground as [Tutorial 0: Background Concepts](00-background.md), but you're driving.

---

## Running the Notebooks

### Quick start

```bash
# From the project root
uv run marimo edit notebooks/00-the-problem.py
```

This opens the notebook in your browser with a live Python kernel. Edit any cell and everything downstream updates automatically.

### Dependencies

The notebooks declare their own dependencies via [PEP 723 inline metadata](https://peps.python.org/pep-0723/). Marimo + `uv` will auto-install them. You don't need to install anything beyond:

```bash
# If you don't have marimo yet
uv add --group dev marimo
```

### Read-only mode

If you just want to read without editing:

```bash
uv run marimo run notebooks/00-the-problem.py
```

A pre-rendered HTML export is also available at `notebooks/00-the-problem.html` for offline viewing.

---

## How Notebooks Map to Tutorials

| Notebook | Tutorial | What you'll learn |
|----------|----------|-------------------|
| `00-the-problem.py` | [Background Concepts](00-background.md) | Explore-exploit tradeoff, why naive strategies fail |
| *coming soon* | [Beta Distribution](01-beta-distribution.md) | Shape of uncertainty, how beliefs update |
| *coming soon* | [Bayesian Updates](02-bayesian-updates.md) | Prior → evidence → posterior, live |
| *coming soon* | [Thompson Sampling](03-thompson-sampling.md) | The algorithm buildlog actually uses |
| *coming soon* | [Contextual Bandits](04-contextual-bandits.md) | Context-dependent rule selection |

---

## Why Marimo?

Buildlog's learning engine uses real math — Beta distributions, Bayesian conjugate updates, Thompson Sampling. Reading about these is fine. But the intuition clicks when you can:

- Drag a slider to change the prior and watch the posterior shift
- Simulate 1,000 bandit rounds and see regret curves form
- Break the algorithm on purpose and understand *why* it broke

That's what these notebooks are for. The tutorials are the textbook. The notebooks are the lab.
