# Tutorial 2: Bayesian Updates

**Learning from Feedback**

This tutorial covers the mechanics of Bayesian inference—how beliefs change when you observe data. We'll derive the Beta-Bernoulli update rule, visualize the learning process, and understand why this conjugate pair is so powerful.

By the end, you'll be able to trace exactly how each observation shifts your belief distribution.

---

## Table of Contents

1. [The Bayesian Recipe](#the-bayesian-recipe)
2. [Prior → Likelihood → Posterior](#prior--likelihood--posterior)
3. [Why Beta-Bernoulli is Conjugate](#why-beta-bernoulli-is-conjugate)
4. [The Update Rule](#the-update-rule)
5. [Visualizing Updates](#visualizing-updates)
6. [Partial Rewards](#partial-rewards)
7. [Batch Updates](#batch-updates)
8. [Code Walkthrough: update()](#code-walkthrough-update)
9. [Common Pitfalls](#common-pitfalls)
10. [Exercises](#exercises)

---

## The Bayesian Recipe

### Beliefs as Distributions

In Bayesian inference, we don't say "the rate is 0.7." We say "here's my distribution of beliefs about possible rates."

```
Frequentist: "The observed rate is 70%."
Bayesian:    "Given my prior and data, here's my full belief distribution."
```

The distribution encodes both our estimate AND our uncertainty.

### The Update Process

When new data arrives, we update our beliefs:

```
┌─────────────┐      ┌────────────┐      ┌─────────────┐
│    PRIOR    │  +   │    DATA    │  →   │  POSTERIOR  │
│  (before)   │      │ (observed) │      │   (after)   │
└─────────────┘      └────────────┘      └─────────────┘
```

The posterior becomes the prior for the next update. Learning is iterative.

```python
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
import random

def visualize_update_process():
    """Show prior → likelihood → posterior conceptually."""
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    x = np.linspace(0, 1, 1000)

    # Prior: Beta(3, 3) - mild belief around 0.5
    prior_a, prior_b = 3, 3
    prior_pdf = stats.beta.pdf(x, prior_a, prior_b)

    # Data: 7 successes out of 10 trials
    successes, trials = 7, 10
    failures = trials - successes

    # Likelihood: Binomial probability of data given each possible rate
    # P(data | rate) ∝ rate^successes × (1-rate)^failures
    likelihood = (x ** successes) * ((1 - x) ** failures)
    likelihood = likelihood / likelihood.max()  # Normalize for visualization

    # Posterior: Beta(prior_a + successes, prior_b + failures)
    post_a = prior_a + successes
    post_b = prior_b + failures
    posterior_pdf = stats.beta.pdf(x, post_a, post_b)

    # Plot
    ax = axes[0]
    ax.plot(x, prior_pdf, 'b-', linewidth=2)
    ax.fill_between(x, prior_pdf, alpha=0.3)
    ax.axvline(prior_a / (prior_a + prior_b), color='red', linestyle='--')
    ax.set_title(f'Prior: Beta({prior_a}, {prior_b})\nMean = {prior_a/(prior_a+prior_b):.2f}')
    ax.set_xlabel('rate')
    ax.set_ylabel('density')

    ax = axes[1]
    ax.plot(x, likelihood, 'g-', linewidth=2)
    ax.fill_between(x, likelihood, alpha=0.3, color='green')
    ax.axvline(successes / trials, color='red', linestyle='--')
    ax.set_title(f'Likelihood: {successes}/{trials} successes\nMLE = {successes/trials:.2f}')
    ax.set_xlabel('rate')
    ax.set_ylabel('relative likelihood')

    ax = axes[2]
    ax.plot(x, prior_pdf, 'b-', linewidth=1, alpha=0.5, label='Prior')
    ax.plot(x, likelihood * 3, 'g-', linewidth=1, alpha=0.5, label='Likelihood (scaled)')
    ax.legend()
    ax.set_title('Prior × Likelihood')
    ax.set_xlabel('rate')

    ax = axes[3]
    ax.plot(x, posterior_pdf, 'purple', linewidth=2)
    ax.fill_between(x, posterior_pdf, alpha=0.3, color='purple')
    ax.axvline(post_a / (post_a + post_b), color='red', linestyle='--')
    ax.set_title(f'Posterior: Beta({post_a}, {post_b})\nMean = {post_a/(post_a+post_b):.2f}')
    ax.set_xlabel('rate')
    ax.set_ylabel('density')

    plt.tight_layout()
    plt.savefig('update_process.png', dpi=150)
    plt.show()

visualize_update_process()
```

---

## Prior → Likelihood → Posterior

### Bayes' Theorem

The mathematical foundation:

```
P(θ|D) = P(D|θ) × P(θ) / P(D)
```

Where:
- **P(θ)** = Prior: What we believed before seeing data
- **P(D|θ)** = Likelihood: How probable is this data if θ were true?
- **P(D)** = Evidence: Total probability of seeing this data (normalizing constant)
- **P(θ|D)** = Posterior: What we believe after seeing data

### In Practice: Proportionality

We often skip P(D) because it's just a normalizing constant:

```
P(θ|D) ∝ P(D|θ) × P(θ)
Posterior ∝ Likelihood × Prior
```

Then normalize at the end so the posterior integrates to 1.

### For Beta-Bernoulli

Let θ be the unknown success rate.

**Prior:** θ ~ Beta(α, β)
```
P(θ) ∝ θ^(α-1) × (1-θ)^(β-1)
```

**Likelihood:** Given n Bernoulli trials with s successes and f = n - s failures:
```
P(D|θ) = θ^s × (1-θ)^f
```

**Posterior:**
```
P(θ|D) ∝ P(D|θ) × P(θ)
       ∝ θ^s × (1-θ)^f × θ^(α-1) × (1-θ)^(β-1)
       = θ^(s+α-1) × (1-θ)^(f+β-1)
       ∝ Beta(α+s, β+f)
```

**The posterior is another Beta distribution!**

---

## Why Beta-Bernoulli is Conjugate

### Definition of Conjugate Prior

A prior is **conjugate** to a likelihood if the posterior has the same distributional form as the prior.

```
Prior:     Beta(α, β)
Likelihood: Bernoulli
Posterior: Beta(α', β')  ← Same family!
```

### Why This Matters

**Without conjugacy:**
```python
# Pseudocode for general Bayesian update
def update_general(prior_samples, likelihood_func, data):
    # Need Monte Carlo / MCMC / Variational Inference
    posterior_samples = []
    for _ in range(10000):
        theta = sample_from_prior()
        weight = likelihood_func(data, theta)
        # Importance sampling, rejection sampling, etc.
        # ... complex, approximate, slow
    return posterior_samples
```

**With conjugacy:**
```python
# Beta-Bernoulli update
def update_conjugate(alpha, beta, successes, failures):
    return alpha + successes, beta + failures  # That's it!
```

Two additions. O(1). Exact.

### Other Conjugate Pairs

| Prior | Likelihood | Posterior | Use Case |
|-------|------------|-----------|----------|
| Beta(α, β) | Bernoulli | Beta(α+s, β+f) | Binary outcomes |
| Dirichlet(α) | Categorical | Dirichlet(α+counts) | Multi-class |
| Gamma(α, β) | Poisson | Gamma(α+sum, β+n) | Count data |
| Normal(μ, σ²) | Normal (known σ²) | Normal(μ', σ'²) | Continuous |

---

## The Update Rule

### Single Observation

For one Bernoulli observation (success = 1, failure = 0):

```python
def update_single(alpha, beta, observation):
    """Update Beta parameters with single binary observation."""
    if observation == 1:
        return alpha + 1, beta
    else:
        return alpha, beta + 1
```

Or more compactly:

```python
def update_single(alpha, beta, reward):
    """Update with reward in [0, 1]."""
    return alpha + reward, beta + (1 - reward)
```

### Multiple Observations

For n trials with s successes:

```python
def update_batch(alpha, beta, successes, failures):
    """Update Beta parameters with batch of observations."""
    return alpha + successes, beta + failures
```

Order doesn't matter! These are equivalent:

```python
# Sequential updates
a, b = 1, 1
for obs in [1, 1, 0, 1, 0]:
    a, b = update_single(a, b, obs)
# Result: (4, 3)

# Batch update
a, b = update_batch(1, 1, successes=3, failures=2)
# Result: (4, 3)
```

### The Math is Trivial

```
New α = Old α + successes
New β = Old β + failures
```

That's the entire algorithm.

---

## Visualizing Updates

### Sequential Updates

Watch the distribution change with each observation:

```python
def visualize_sequential_updates():
    """Show how distribution evolves with each observation."""
    observations = [1, 1, 0, 1, 1, 1, 0, 1, 0, 1]  # 7 successes, 3 failures

    fig, axes = plt.subplots(2, 5, figsize=(18, 7))
    x = np.linspace(0, 1, 1000)

    alpha, beta = 1, 1  # Start uniform

    for i, ax in enumerate(axes.flat):
        pdf = stats.beta.pdf(x, alpha, beta)
        ax.plot(x, pdf, 'steelblue', linewidth=2)
        ax.fill_between(x, pdf, alpha=0.3)

        mean = alpha / (alpha + beta)
        ax.axvline(mean, color='red', linestyle='--', label=f'Mean: {mean:.2f}')
        ax.axvline(0.7, color='green', linestyle=':', alpha=0.5, label='True: 0.70')

        if i == 0:
            ax.set_title(f'Prior\nBeta({alpha}, {beta})')
        else:
            obs = observations[i-1]
            ax.set_title(f'After obs {i}: {"✓" if obs else "✗"}\nBeta({alpha}, {beta})')

        ax.set_xlim(0, 1)
        ax.set_xlabel('rate')

        if i == 0:
            ax.legend(fontsize=7)

        # Update for next iteration
        if i < len(observations):
            obs = observations[i]
            alpha += obs
            beta += (1 - obs)

    plt.tight_layout()
    plt.savefig('sequential_updates.png', dpi=150)
    plt.show()

visualize_sequential_updates()
```

### The Tug-of-War

Successes pull right, failures pull left:

```python
def visualize_tug_of_war():
    """Show how successes and failures pull the distribution."""
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    x = np.linspace(0, 1, 1000)

    scenarios = [
        ((5, 5), "Balanced: 4W, 4L\nMean = 0.50"),
        ((8, 2), "Winning: 7W, 1L\nMean = 0.80"),
        ((2, 8), "Losing: 1W, 7L\nMean = 0.20"),
        ((5, 2), "Slightly ahead: 4W, 1L\nMean = 0.71"),
    ]

    for ax, ((a, b), title) in zip(axes, scenarios):
        pdf = stats.beta.pdf(x, a, b)
        ax.plot(x, pdf, 'steelblue', linewidth=2)
        ax.fill_between(x, pdf, alpha=0.3)
        ax.axvline(a / (a + b), color='red', linestyle='--')
        ax.set_title(f'Beta({a}, {b})\n{title}')
        ax.set_xlim(0, 1)
        ax.set_xlabel('rate')

    plt.tight_layout()
    plt.savefig('tug_of_war.png', dpi=150)
    plt.show()

visualize_tug_of_war()
```

### Convergence to Truth

With enough data, the posterior concentrates on the true rate:

```python
def visualize_convergence():
    """Show posterior concentrating on true rate."""
    true_rate = 0.65
    random.seed(42)

    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    x = np.linspace(0, 1, 1000)

    checkpoints = [0, 5, 10, 25, 50, 100, 200, 500]
    alpha, beta = 1, 1

    all_obs = [1 if random.random() < true_rate else 0 for _ in range(500)]

    for ax, n in zip(axes.flat, checkpoints):
        # Update to this checkpoint
        if n > 0:
            successes = sum(all_obs[:n])
            failures = n - successes
            alpha = 1 + successes
            beta = 1 + failures

        pdf = stats.beta.pdf(x, alpha, beta)
        ax.plot(x, pdf, 'steelblue', linewidth=2)
        ax.fill_between(x, pdf, alpha=0.3)

        ax.axvline(true_rate, color='green', linewidth=2, label='True rate')
        ax.axvline(alpha / (alpha + beta), color='red', linestyle='--', label='Posterior mean')

        # 95% CI
        lo = stats.beta.ppf(0.025, alpha, beta)
        hi = stats.beta.ppf(0.975, alpha, beta)

        ax.set_title(f'n={n}\nMean={alpha/(alpha+beta):.3f}, 95% CI=[{lo:.2f}, {hi:.2f}]')
        ax.set_xlim(0, 1)

        if n == 0:
            ax.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig('convergence_to_truth.png', dpi=150)
    plt.show()

visualize_convergence()
```

---

## Partial Rewards

### Beyond Binary: Continuous Rewards

Sometimes feedback isn't just 0 or 1. You might have:
- "Mostly helped" → 0.8
- "Partially helped" → 0.5
- "Didn't really help" → 0.2

The update rule still works:

```python
def update(alpha, beta, reward):
    """
    Update with continuous reward in [0, 1].

    Interpretation: reward=0.7 means
    "70% of a success, 30% of a failure"
    """
    return alpha + reward, beta + (1 - reward)
```

### Example: Partial Credit

```python
def partial_reward_example():
    """Compare binary vs partial rewards."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    x = np.linspace(0, 1, 1000)

    # Scenario: 5 observations, true effect is "moderately helpful" (0.6)

    # Binary (harsh): everything below 0.5 is failure
    binary_alpha = 1 + 3  # 3 "successes"
    binary_beta = 1 + 2   # 2 "failures"

    # Partial (nuanced): actual values [0.7, 0.5, 0.6, 0.8, 0.4]
    rewards = [0.7, 0.5, 0.6, 0.8, 0.4]
    partial_alpha = 1 + sum(rewards)
    partial_beta = 1 + sum(1 - r for r in rewards)

    # Plot
    ax = axes[0]
    pdf = stats.beta.pdf(x, binary_alpha, binary_beta)
    ax.plot(x, pdf, 'steelblue', linewidth=2)
    ax.fill_between(x, pdf, alpha=0.3)
    ax.axvline(binary_alpha / (binary_alpha + binary_beta), color='red', linestyle='--')
    ax.set_title(f'Binary Rewards\nBeta({binary_alpha}, {binary_beta})\nMean = {binary_alpha/(binary_alpha+binary_beta):.2f}')
    ax.set_xlim(0, 1)

    ax = axes[1]
    pdf = stats.beta.pdf(x, partial_alpha, partial_beta)
    ax.plot(x, pdf, 'steelblue', linewidth=2)
    ax.fill_between(x, pdf, alpha=0.3)
    ax.axvline(partial_alpha / (partial_alpha + partial_beta), color='red', linestyle='--')
    ax.set_title(f'Partial Rewards\nBeta({partial_alpha:.1f}, {partial_beta:.1f})\nMean = {partial_alpha/(partial_alpha+partial_beta):.2f}')
    ax.set_xlim(0, 1)

    ax = axes[2]
    pdf1 = stats.beta.pdf(x, binary_alpha, binary_beta)
    pdf2 = stats.beta.pdf(x, partial_alpha, partial_beta)
    ax.plot(x, pdf1, 'b-', linewidth=2, label='Binary', alpha=0.7)
    ax.plot(x, pdf2, 'g-', linewidth=2, label='Partial', alpha=0.7)
    ax.axvline(0.6, color='red', linestyle=':', linewidth=2, label='True effect')
    ax.legend()
    ax.set_title('Comparison\nPartial rewards preserve more information')
    ax.set_xlim(0, 1)

    plt.tight_layout()
    plt.savefig('partial_rewards.png', dpi=150)
    plt.show()

partial_reward_example()
```

### When to Use Partial Rewards

| Signal | Binary | Partial |
|--------|--------|---------|
| Click/no-click | ✓ | |
| Code review: accepted/rejected | ✓ | |
| User rating 1-5 | | ✓ (scale to [0,1]) |
| Revision distance | | ✓ (1 - distance) |
| Partial task completion | | ✓ |

In buildlog, we use partial rewards for revision distance:
- `reward = 1.0` → Accepted as-is
- `reward = 0.7` → Minor revision needed
- `reward = 0.3` → Major revision needed
- `reward = 0.0` → Rejected entirely

---

## Batch Updates

### Order Independence

Bayesian updates are **exchangeable**—order doesn't matter:

```python
def prove_order_independence():
    """Show that update order doesn't affect final posterior."""
    observations = [1, 0, 1, 1, 0, 1]

    # Order 1: As given
    a1, b1 = 1, 1
    for obs in observations:
        a1 += obs
        b1 += (1 - obs)

    # Order 2: Reversed
    a2, b2 = 1, 1
    for obs in reversed(observations):
        a2 += obs
        b2 += (1 - obs)

    # Order 3: Shuffled
    import random
    shuffled = observations.copy()
    random.shuffle(shuffled)
    a3, b3 = 1, 1
    for obs in shuffled:
        a3 += obs
        b3 += (1 - obs)

    # Order 4: Batch
    a4 = 1 + sum(observations)
    b4 = 1 + len(observations) - sum(observations)

    print("All orders produce same posterior:")
    print(f"  Original order: Beta({a1}, {b1})")
    print(f"  Reversed:       Beta({a2}, {b2})")
    print(f"  Shuffled:       Beta({a3}, {b3})")
    print(f"  Batch:          Beta({a4}, {b4})")

prove_order_independence()
```

Output:
```
All orders produce same posterior:
  Original order: Beta(5, 3)
  Reversed:       Beta(5, 3)
  Shuffled:       Beta(5, 3)
  Batch:          Beta(5, 3)
```

### Batch Update Formula

```python
def batch_update(alpha, beta, rewards):
    """
    Update with multiple rewards at once.

    Equivalent to sequential updates but more efficient.
    """
    total_reward = sum(rewards)
    total_penalty = len(rewards) - total_reward
    return alpha + total_reward, beta + total_penalty
```

### When Batching Helps

In buildlog, we sometimes update multiple rules with the same feedback:

```python
# A mistake happened → all active rules get negative feedback
active_rules = ['rule-1', 'rule-2', 'rule-3']
for rule_id in active_rules:
    bandit.update(rule_id, reward=0, context='type-errors')
```

Each rule gets updated independently, but within a rule, multiple observations can be batched.

---

## Code Walkthrough: update()

From `src/buildlog/core/bandit.py`:

```python
def update(self, reward: float) -> None:
    """Update posterior with observed reward.

    For Bernoulli rewards (0 or 1), this is exact Bayesian inference.
    For continuous rewards in [0, 1], this is an approximation that
    still works well in practice.

    Args:
        reward: Observed reward, typically in [0, 1].
               - 1.0 = full success (rule helped)
               - 0.0 = failure (rule didn't help)
               - Values in between for partial credit
    """
    self.alpha += reward
    self.beta += (1.0 - reward)
```

### Line-by-Line

```python
self.alpha += reward
```
- If reward=1: α increases by 1 (full success)
- If reward=0.7: α increases by 0.7 (partial success)
- Shifts the mean toward 1

```python
self.beta += (1.0 - reward)
```
- If reward=1: β stays same (no failure evidence)
- If reward=0: β increases by 1 (full failure)
- If reward=0.7: β increases by 0.3 (partial failure)
- Shifts the mean toward 0

### The Invariant

After update: `α + β = (old α + old β) + 1`

One observation always adds 1 to the total pseudo-count. The reward determines how that 1 is split between α and β.

```python
def verify_invariant():
    alpha, beta = 3.0, 2.0
    old_total = alpha + beta

    for reward in [0.0, 0.3, 0.5, 0.7, 1.0]:
        new_alpha = alpha + reward
        new_beta = beta + (1 - reward)
        new_total = new_alpha + new_beta
        print(f"reward={reward}: total goes from {old_total} to {new_total}")

verify_invariant()
```

Output:
```
reward=0.0: total goes from 5.0 to 6.0
reward=0.3: total goes from 5.0 to 6.0
reward=0.5: total goes from 5.0 to 6.0
reward=0.7: total goes from 5.0 to 6.0
reward=1.0: total goes from 5.0 to 6.0
```

---

## Common Pitfalls

### Pitfall 1: Forgetting the Prior

```python
# WRONG: Starting from scratch each time
def bad_update(observations):
    successes = sum(observations)
    failures = len(observations) - successes
    return successes, failures  # Missing prior!

# RIGHT: Include prior
def good_update(observations, prior_alpha=1, prior_beta=1):
    successes = sum(observations)
    failures = len(observations) - successes
    return prior_alpha + successes, prior_beta + failures
```

### Pitfall 2: Overconfident Priors

```python
# Too strong: 100 pseudo-observations before seeing any data
strong_prior = BetaParams(alpha=50, beta=50)  # Mean=0.5, very confident

# After 10 observations (8 successes):
# Beta(58, 52) → Mean = 0.53
# Real data barely moved the needle!

# Better: Weak prior that lets data speak
weak_prior = BetaParams(alpha=1, beta=1)
# After same 10 observations:
# Beta(9, 3) → Mean = 0.75
# Data dominates as it should
```

### Pitfall 3: Not Accounting for Uncertainty

```python
# WRONG: Just use the mean
rule_a_mean = 0.65  # 6 successes, 4 failures
rule_b_mean = 0.60  # 60 successes, 40 failures

if rule_a_mean > rule_b_mean:
    print("A is better!")  # But we're way less certain about A!

# RIGHT: Consider the full distribution
# Rule A: Beta(7, 5) — wide, uncertain
# Rule B: Beta(61, 41) — narrow, confident
# A might be better, but B is a safer bet
```

### Pitfall 4: Negative or Zero Parameters

```python
# WRONG: Can happen with buggy reward signals
alpha = 1.0
alpha += -0.5  # Bug! Rewards should be non-negative
# Now alpha = 0.5, which is valid but unexpected

# If alpha or beta reach 0 or below, you get errors:
try:
    params = BetaParams(alpha=0, beta=1)
except ValueError as e:
    print(f"Caught: {e}")
```

---

## Exercises

### Conceptual Exercises

**Exercise 2.1: Update Calculation**

Starting from Beta(1, 1), compute the posterior after observing: success, success, failure, success.

<details>
<summary>Solution</summary>

```
Start: Beta(1, 1)
After success: Beta(2, 1)
After success: Beta(3, 1)
After failure: Beta(3, 2)
After success: Beta(4, 2)

Final: Beta(4, 2), Mean = 0.667
```

Or directly: 3 successes, 1 failure
```
Beta(1 + 3, 1 + 1) = Beta(4, 2)
```

</details>

---

**Exercise 2.2: Prior Strength**

You have two analysts:
- Alice uses prior Beta(1, 1)
- Bob uses prior Beta(10, 10)

Both observe 8 successes out of 10 trials. What are their posteriors?

<details>
<summary>Solution</summary>

**Alice:**
```
Beta(1 + 8, 1 + 2) = Beta(9, 3)
Mean = 0.75
```

**Bob:**
```
Beta(10 + 8, 10 + 2) = Beta(18, 12)
Mean = 0.60
```

Bob's strong prior (centered at 0.5) pulls his posterior toward 0.5 even though data suggests 0.8. Alice's weak prior lets data dominate.

</details>

---

**Exercise 2.3: Information Content**

Which provides more information: observing 10 successes out of 10 trials, or 100 successes out of 100 trials?

<details>
<summary>Solution</summary>

Both have the same observed rate (100%), but 100/100 provides **more information**.

After 10/10 with Beta(1,1) prior:
```
Beta(11, 1), Mean = 0.917, 95% CI ≈ [0.73, 0.99]
```

After 100/100 with Beta(1,1) prior:
```
Beta(101, 1), Mean = 0.990, 95% CI ≈ [0.96, 1.00]
```

More observations → narrower confidence interval → more certain.

</details>

---

### Coding Exercises

**Exercise 2.4: Implement Sequential Visualizer**

Write a function that animates Bayesian updates:

```python
def animate_updates(observations, interval=500):
    """
    Create an animation showing posterior evolution.

    Args:
        observations: List of 0s and 1s
        interval: Milliseconds between frames
    """
    # YOUR CODE HERE
    # Use matplotlib.animation.FuncAnimation
    pass
```

<details>
<summary>Solution</summary>

```python
from matplotlib.animation import FuncAnimation
from IPython.display import HTML

def animate_updates(observations, interval=500):
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.linspace(0, 1, 1000)

    line, = ax.plot([], [], 'steelblue', linewidth=2)
    fill = ax.fill_between([], [], alpha=0.3)
    title = ax.set_title('')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 10)
    ax.set_xlabel('rate')
    ax.set_ylabel('density')

    alpha, beta = 1, 1
    history = [(alpha, beta)]
    for obs in observations:
        alpha += obs
        beta += (1 - obs)
        history.append((alpha, beta))

    def init():
        line.set_data([], [])
        return line,

    def update(frame):
        ax.clear()
        a, b = history[frame]
        pdf = stats.beta.pdf(x, a, b)
        ax.plot(x, pdf, 'steelblue', linewidth=2)
        ax.fill_between(x, pdf, alpha=0.3)
        ax.axvline(a / (a + b), color='red', linestyle='--')
        ax.set_xlim(0, 1)
        ax.set_ylim(0, max(pdf) * 1.2)
        ax.set_xlabel('rate')
        ax.set_ylabel('density')

        if frame == 0:
            ax.set_title(f'Prior: Beta({a}, {b})')
        else:
            obs = observations[frame - 1]
            ax.set_title(f'After {frame} obs (last: {"✓" if obs else "✗"}): Beta({a}, {b}), Mean={a/(a+b):.2f}')

        return ax,

    anim = FuncAnimation(fig, update, init_func=init,
                         frames=len(history), interval=interval, blit=False)
    return anim

# Usage:
# anim = animate_updates([1, 1, 0, 1, 0, 1, 1, 1, 0, 1])
# HTML(anim.to_jshtml())  # In Jupyter
```

</details>

---

**Exercise 2.5: Prior Sensitivity Analysis**

Write code to analyze how different priors converge to the same posterior:

```python
def prior_convergence_analysis(true_rate, priors, n_observations):
    """
    For each prior, simulate learning and track posterior mean over time.
    Show that all priors eventually converge to the true rate.
    """
    # YOUR CODE HERE
    pass

priors = {
    'Uniform': (1, 1),
    'Optimistic': (5, 1),
    'Pessimistic': (1, 5),
    'Confident Wrong': (20, 20),
}
prior_convergence_analysis(true_rate=0.7, priors=priors, n_observations=200)
```

<details>
<summary>Solution</summary>

```python
def prior_convergence_analysis(true_rate, priors, n_observations):
    random.seed(42)
    observations = [1 if random.random() < true_rate else 0
                    for _ in range(n_observations)]

    plt.figure(figsize=(12, 6))

    for name, (a0, b0) in priors.items():
        means = []
        alpha, beta = a0, b0

        for i in range(n_observations + 1):
            means.append(alpha / (alpha + beta))
            if i < n_observations:
                alpha += observations[i]
                beta += (1 - observations[i])

        plt.plot(means, label=f'{name}: Beta({a0}, {b0})', linewidth=2)

    plt.axhline(true_rate, color='black', linestyle='--', linewidth=2, label=f'True rate: {true_rate}')
    plt.xlabel('Observations')
    plt.ylabel('Posterior Mean')
    plt.title('Prior Convergence: All Roads Lead to Truth')
    plt.legend()
    plt.savefig('prior_convergence.png', dpi=150)
    plt.show()
```

</details>

---

**Exercise 2.6: Implement Forgetting**

In non-stationary environments, old observations should count less. Implement an update with exponential decay:

```python
class DecayingBetaParams:
    """Beta parameters with exponential decay for non-stationary environments."""

    def __init__(self, alpha=1.0, beta=1.0, decay=0.99):
        self.alpha = alpha
        self.beta = beta
        self.decay = decay

    def update(self, reward):
        """Update with decay: old observations fade."""
        # YOUR CODE HERE
        pass

    def mean(self):
        return self.alpha / (self.alpha + self.beta)
```

<details>
<summary>Solution</summary>

```python
class DecayingBetaParams:
    def __init__(self, alpha=1.0, beta=1.0, decay=0.99):
        self.alpha = alpha
        self.beta = beta
        self.decay = decay
        self.prior_alpha = alpha
        self.prior_beta = beta

    def update(self, reward):
        # Decay existing pseudo-counts toward prior
        self.alpha = self.prior_alpha + self.decay * (self.alpha - self.prior_alpha)
        self.beta = self.prior_beta + self.decay * (self.beta - self.prior_beta)

        # Add new observation
        self.alpha += reward
        self.beta += (1 - reward)

    def mean(self):
        return self.alpha / (self.alpha + self.beta)

# Test: sudden change in true rate
params = DecayingBetaParams(decay=0.95)

# First 50 observations: rate = 0.8
for _ in range(50):
    params.update(1 if random.random() < 0.8 else 0)
print(f"After 50 obs (rate=0.8): mean = {params.mean():.2f}")

# Next 50 observations: rate changes to 0.2
for _ in range(50):
    params.update(1 if random.random() < 0.2 else 0)
print(f"After 100 obs (rate changed to 0.2): mean = {params.mean():.2f}")
```

</details>

---

### Challenge Exercises

**Exercise 2.7: Derive the Variance Formula**

Starting from the definition of variance and the Beta PDF, derive:

```
Var[X] = αβ / ((α + β)² × (α + β + 1))
```

Hint: Use E[X²] - E[X]² and the fact that E[X^n] for Beta involves the Beta function.

<details>
<summary>Hint</summary>

For Beta(α, β):
```
E[X] = α / (α + β)
E[X²] = α(α + 1) / ((α + β)(α + β + 1))

Var[X] = E[X²] - E[X]²
```

</details>

---

**Exercise 2.8: Thompson Sampling Preview**

Given these two arms:
- A: Beta(3, 2) — mean 0.60
- B: Beta(6, 4) — mean 0.60

Both have the same mean. Run 10,000 Thompson Sampling selections (sample from each, pick higher). Which arm gets selected more often? Why?

```python
def thompson_selection_comparison(arm_a, arm_b, n_trials=10000):
    """Count how often each arm is selected via Thompson Sampling."""
    # YOUR CODE HERE
    pass
```

<details>
<summary>Solution</summary>

```python
def thompson_selection_comparison(arm_a, arm_b, n_trials=10000):
    a_alpha, a_beta = arm_a
    b_alpha, b_beta = arm_b

    a_selected = 0
    for _ in range(n_trials):
        sample_a = random.betavariate(a_alpha, a_beta)
        sample_b = random.betavariate(b_alpha, b_beta)
        if sample_a > sample_b:
            a_selected += 1

    print(f"Arm A selected: {a_selected / n_trials:.1%}")
    print(f"Arm B selected: {(n_trials - a_selected) / n_trials:.1%}")

thompson_selection_comparison((3, 2), (6, 4))
# Result: ~50/50, because same mean

# But variance differs:
var_a = (3 * 2) / ((5) ** 2 * 6)  # = 0.04
var_b = (6 * 4) / ((10) ** 2 * 11)  # = 0.022

print(f"\nVariance A: {var_a:.4f}")
print(f"Variance B: {var_b:.4f}")
# A has higher variance → more extreme samples → occasionally very high OR very low
# Selection is 50/50 on average, but A's samples are more spread out
```

</details>

---

**Exercise 2.9: Credible Interval Calibration**

Check if 95% credible intervals are actually calibrated. Generate many datasets from a known true rate, compute posterior 95% CIs, and verify that ~95% contain the true rate.

```python
def calibration_check(true_rate, n_observations, n_simulations=1000):
    """
    Check if 95% credible intervals have 95% coverage.
    """
    # YOUR CODE HERE
    pass

calibration_check(true_rate=0.7, n_observations=50)
# Should print coverage close to 95%
```

<details>
<summary>Solution</summary>

```python
def calibration_check(true_rate, n_observations, n_simulations=1000):
    contains_true = 0

    for _ in range(n_simulations):
        # Generate data
        observations = [1 if random.random() < true_rate else 0
                        for _ in range(n_observations)]

        # Compute posterior
        alpha = 1 + sum(observations)
        beta = 1 + n_observations - sum(observations)

        # 95% CI
        lower = stats.beta.ppf(0.025, alpha, beta)
        upper = stats.beta.ppf(0.975, alpha, beta)

        if lower <= true_rate <= upper:
            contains_true += 1

    coverage = contains_true / n_simulations
    print(f"95% CI coverage: {coverage:.1%} (expected: 95%)")

calibration_check(true_rate=0.7, n_observations=50)
# Output: 95% CI coverage: 94.8% (expected: 95%)
```

</details>

---

## Summary

You now understand:

1. **Bayes' theorem:** Posterior ∝ Likelihood × Prior
2. **Conjugacy:** Beta-Bernoulli gives tractable, exact updates
3. **The update rule:** α += reward, β += (1 - reward)
4. **Order independence:** Batch updates equal sequential updates
5. **Partial rewards:** Continuous [0, 1] rewards work too
6. **Convergence:** Posteriors concentrate on truth with enough data

In **Tutorial 3**, we'll see how Thompson Sampling uses these distributions to make intelligent explore-exploit decisions.

---

*Previous: [Tutorial 1: Beta Distribution Deep Dive](./01-beta-distribution.md)*

*Next: [Tutorial 3: Thompson Sampling](./03-thompson-sampling.md)*
