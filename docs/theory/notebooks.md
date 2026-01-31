# Interactive Notebooks

**The hands-on course for the theory behind buildlog.**

The tutorials in this section explain the *what* and *why* — multi-armed bandits, Beta distributions, Bayesian updates, Thompson Sampling, contextual bandits. The interactive notebooks let you *play with the machinery yourself*.

These are [Marimo](https://marimo.io) notebooks: reactive Python notebooks that run in your browser. Every cell re-executes when you change an input, so you can drag sliders, tweak parameters, and watch the math respond in real time. No Jupyter kernel restarts, no stale state.

---

## Available Notebooks

### 0. On Learning What Works

**File:** `notebooks/00-the-problem.py` | [View rendered notebook](../notebooks/00-the-problem.md)

The explore-exploit tradeoff, from first principles. Why do agents need to balance trying new things against sticking with what works? This notebook lets you simulate the tension directly — pull slot machine arms, watch regret accumulate, and build intuition for why naive strategies fail.

Covers the same ground as [Tutorial 0: Background Concepts](00-background.md), but you're driving.

!!! tip "Run it"

    **[View the rendered notebook](../notebooks/00-the-problem.md)** — the full Marimo output, right in the docs.

    **Run it live** (interactive, with sliders and editable cells):
    ```bash
    uv run marimo edit notebooks/00-the-problem.py
    ```

---

## Running the Notebooks

### Quick start

```bash
# Clone the repo
git clone https://github.com/Peleke/buildlog-template && cd buildlog-template

# Run any notebook interactively
uv run marimo edit notebooks/00-the-problem.py
```

### Dependencies

The notebooks declare their own dependencies via [PEP 723 inline metadata](https://peps.python.org/pep-0723/). Marimo + `uv` will auto-install them. You don't need to install anything beyond:

```bash
# If you don't have marimo yet
uv add --group dev marimo
```

### Pre-rendered HTML

Each notebook has a pre-rendered `.html` export in the `notebooks/` directory for offline viewing or quick demos. These are self-contained — no server needed, just open in a browser.

---

## How Notebooks Map to Tutorials

| Notebook | Tutorial | What you'll learn |
|----------|----------|-------------------|
| [`00-the-problem.py`](../notebooks/00-the-problem.md) | [Background Concepts](00-background.md) | Explore-exploit tradeoff, why naive strategies fail |
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
