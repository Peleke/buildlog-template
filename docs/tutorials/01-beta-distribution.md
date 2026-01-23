# Tutorial 1: Beta Distribution Deep Dive

**Understanding Your Uncertainty**

The Beta distribution is your primary tool for modeling unknown probabilities. This tutorial goes deep: we'll understand why it's perfect for binary outcomes, visualize how it behaves, and walk through buildlog's `BetaParams` implementation line by line.

By the end, you'll be able to look at `Beta(α, β)` parameters and immediately understand what they mean about your beliefs.

---

## Table of Contents

1. [Why Beta?](#why-beta)
2. [The Parameterization](#the-parameterization)
3. [Visualizing Beta Distributions](#visualizing-beta-distributions)
4. [The Uniform Prior Beta(1,1)](#the-uniform-prior-beta11)
5. [How Data Narrows the Distribution](#how-data-narrows-the-distribution)
6. [The Math: Mean and Variance](#the-math-mean-and-variance)
7. [Code Walkthrough: BetaParams](#code-walkthrough-betaparams)
8. [Interactive Examples](#interactive-examples)
9. [Exercises](#exercises)

---

## Why Beta?

### The Problem: Modeling Unknown Probabilities

You have a rule. It either helps (1) or doesn't help (0). After observing some outcomes, you want to estimate the true "help rate"—a probability between 0 and 1.

What distribution should you use to represent your belief about this probability?

**Requirements:**
1. Support on [0, 1] (probabilities can't be negative or exceed 1)
2. Flexible shape (can represent "I have no idea" and "I'm very confident")
3. Easy updates (new observations should be trivial to incorporate)
4. Closed-form sampling (we'll need to sample from it efficiently)

The Beta distribution satisfies all four.

### Why Not Other Distributions?

**Normal distribution?** Support is (-∞, +∞). Truncating is awkward.

**Uniform?** Can't express "I think it's around 0.7" or any peaked belief.

**Triangular?** Updates aren't conjugate to Bernoulli.

**Beta?** Perfect match. It's literally designed for this use case.

```python
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

def compare_distributions():
    """Show why Beta is the right choice."""
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    x_wide = np.linspace(-1, 2, 1000)
    x_unit = np.linspace(0, 1, 1000)

    # Normal (wrong domain)
    ax = axes[0]
    pdf = stats.norm.pdf(x_wide, 0.6, 0.15)
    ax.plot(x_wide, pdf, 'b-', linewidth=2)
    ax.fill_between(x_wide, pdf, alpha=0.3)
    ax.axvspan(-1, 0, alpha=0.2, color='red', label='Invalid (<0)')
    ax.axvspan(1, 2, alpha=0.2, color='red', label='Invalid (>1)')
    ax.axvline(0, color='red', linestyle='--')
    ax.axvline(1, color='red', linestyle='--')
    ax.set_title('Normal(0.6, 0.15)\n❌ Leaks outside [0,1]')
    ax.set_xlim(-0.5, 1.5)

    # Uniform (can't peak)
    ax = axes[1]
    pdf = stats.uniform.pdf(x_unit, 0, 1)
    ax.plot(x_unit, pdf, 'b-', linewidth=2)
    ax.fill_between(x_unit, pdf, alpha=0.3)
    ax.set_title('Uniform(0, 1)\n❌ Can\'t express "around 0.7"')
    ax.set_xlim(0, 1)

    # Truncated normal (awkward)
    ax = axes[2]
    a, b = (0 - 0.6) / 0.15, (1 - 0.6) / 0.15
    pdf = stats.truncnorm.pdf(x_unit, a, b, 0.6, 0.15)
    ax.plot(x_unit, pdf, 'b-', linewidth=2)
    ax.fill_between(x_unit, pdf, alpha=0.3)
    ax.set_title('Truncated Normal\n⚠️ Awkward updates')
    ax.set_xlim(0, 1)

    # Beta (perfect)
    ax = axes[3]
    pdf = stats.beta.pdf(x_unit, 12, 8)
    ax.plot(x_unit, pdf, 'b-', linewidth=2)
    ax.fill_between(x_unit, pdf, alpha=0.3)
    ax.set_title('Beta(12, 8)\n✅ Perfect for [0,1]')
    ax.set_xlim(0, 1)

    plt.tight_layout()
    plt.savefig('why_beta.png', dpi=150)
    plt.show()

compare_distributions()
```

---

## The Parameterization

### α and β: Pseudo-Counts

The Beta distribution has two parameters:

| Parameter | Name | Interpretation |
|-----------|------|----------------|
| α (alpha) | Pseudo-successes | Prior + observed successes |
| β (beta) | Pseudo-failures | Prior + observed failures |

**Pseudo-count intuition:** Think of α and β as "imaginary observations" that encode your prior belief.

- **Beta(1, 1):** 0 real observations + (1, 1) prior = "I've imagined 1 success and 1 failure, so my best guess is 50%"
- **Beta(3, 1):** 0 real observations + (3, 1) prior = "I've imagined 3 successes and 1 failure, so I believe success is likely (~75%)"
- **Beta(11, 6):** 10 successes, 5 failures, + (1, 1) prior = "I've seen 10 wins and 5 losses, mean ~65%"

### The Prior Encodes Your Starting Belief

Before seeing any data, what do you believe?

```python
def visualize_priors():
    """Different priors encode different starting beliefs."""
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    x = np.linspace(0, 1, 1000)

    priors = [
        (1, 1, "Beta(1, 1)\nUniform: 'I have no idea'"),
        (0.5, 0.5, "Beta(0.5, 0.5)\nJeffreys: 'Probably extreme'"),
        (2, 5, "Beta(2, 5)\nSkeptical: 'Probably bad (~30%)'"),
        (5, 2, "Beta(5, 2)\nOptimistic: 'Probably good (~70%)'"),
    ]

    for ax, (a, b, title) in zip(axes, priors):
        pdf = stats.beta.pdf(x, a, b)
        ax.plot(x, pdf, 'b-', linewidth=2)
        ax.fill_between(x, pdf, alpha=0.3)
        mean = a / (a + b)
        ax.axvline(mean, color='red', linestyle='--', label=f'Mean: {mean:.2f}')
        ax.set_title(title)
        ax.set_xlabel('Probability')
        ax.legend(fontsize=8)
        ax.set_xlim(0, 1)

    plt.tight_layout()
    plt.savefig('priors.png', dpi=150)
    plt.show()

visualize_priors()
```

In buildlog, we use two priors:

| Source | Prior | Rationale |
|--------|-------|-----------|
| Learned rules | Beta(1, 1) | No prior knowledge, let data decide |
| Seed rules (gauntlet) | Beta(3, 1) | Expert-curated, start optimistic |

---

## Visualizing Beta Distributions

### Shape Depends on α and β

The Beta distribution can take many shapes:

```python
def beta_shape_gallery():
    """Gallery of Beta distribution shapes."""
    fig, axes = plt.subplots(3, 4, figsize=(16, 12))
    x = np.linspace(0.001, 0.999, 1000)  # Avoid endpoints for numerical stability

    shapes = [
        # Row 1: Symmetric
        (1, 1, "Uniform"),
        (2, 2, "Gentle peak"),
        (5, 5, "Moderate peak"),
        (50, 50, "Sharp peak at 0.5"),

        # Row 2: Skewed right (believe high)
        (2, 1, "Skewed right"),
        (5, 2, "More skewed right"),
        (10, 2, "Strongly right"),
        (50, 5, "Very confident high"),

        # Row 3: Skewed left (believe low)
        (1, 2, "Skewed left"),
        (2, 5, "More skewed left"),
        (2, 10, "Strongly left"),
        (5, 50, "Very confident low"),
    ]

    for ax, (a, b, name) in zip(axes.flat, shapes):
        pdf = stats.beta.pdf(x, a, b)
        ax.plot(x, pdf, 'steelblue', linewidth=2)
        ax.fill_between(x, pdf, alpha=0.3)

        mean = a / (a + b)
        ax.axvline(mean, color='red', linestyle='--', alpha=0.7)

        ax.set_title(f'Beta({a}, {b})\n{name}\nμ={mean:.2f}', fontsize=10)
        ax.set_xlim(0, 1)
        ax.set_xlabel('p')
        ax.set_ylabel('density')

    plt.tight_layout()
    plt.savefig('beta_gallery.png', dpi=150)
    plt.show()

beta_shape_gallery()
```

### Key Observations

1. **α = β → Symmetric around 0.5**
2. **α > β → Skewed right (believe high)**
3. **α < β → Skewed left (believe low)**
4. **Large α + β → Narrow peak (high confidence)**
5. **Small α + β → Spread out (high uncertainty)**

### The Extremes: U-Shaped and J-Shaped

```python
def extreme_betas():
    """Beta can be U-shaped or J-shaped."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    x = np.linspace(0.01, 0.99, 1000)

    extremes = [
        (0.5, 0.5, "U-shaped: 'Probably 0 or 1'\nGood for Jeffreys prior"),
        (0.5, 2, "J-shaped left: 'Probably 0'\nStrong pessimism"),
        (2, 0.5, "J-shaped right: 'Probably 1'\nStrong optimism"),
    ]

    for ax, (a, b, title) in zip(axes, extremes):
        pdf = stats.beta.pdf(x, a, b)
        ax.plot(x, pdf, 'steelblue', linewidth=2)
        ax.fill_between(x, pdf, alpha=0.3)
        ax.set_title(f'Beta({a}, {b})\n{title}', fontsize=10)
        ax.set_xlim(0, 1)
        ax.set_xlabel('p')

    plt.tight_layout()
    plt.savefig('extreme_betas.png', dpi=150)
    plt.show()

extreme_betas()
```

**Note:** When α < 1 or β < 1, the PDF goes to infinity at the boundaries. This is valid mathematically (total area is still 1) but can be numerically tricky.

---

## The Uniform Prior Beta(1,1)

### Maximum Uncertainty

Beta(1, 1) is the uniform distribution on [0, 1]:

```python
def uniform_prior():
    """Beta(1,1) is uniform—maximum ignorance."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    x = np.linspace(0, 1, 1000)

    # PDF
    ax = axes[0]
    pdf = stats.beta.pdf(x, 1, 1)
    ax.plot(x, pdf, 'steelblue', linewidth=2)
    ax.fill_between(x, pdf, alpha=0.3)
    ax.set_title('Beta(1, 1) PDF\nConstant density = "any value equally likely"')
    ax.set_xlabel('p')
    ax.set_ylabel('density')
    ax.set_ylim(0, 1.5)

    # CDF
    ax = axes[1]
    cdf = stats.beta.cdf(x, 1, 1)
    ax.plot(x, cdf, 'steelblue', linewidth=2)
    ax.set_title('Beta(1, 1) CDF\nLinear = uniform')
    ax.set_xlabel('p')
    ax.set_ylabel('P(X ≤ p)')

    plt.tight_layout()
    plt.savefig('uniform_prior.png', dpi=150)
    plt.show()

uniform_prior()
```

### Why Start Uniform?

For learned rules, we genuinely have no prior knowledge. Beta(1, 1) says:
- "The true rate could be 0.1, could be 0.9, I truly don't know"
- Mean = 0.5 (best guess without data)
- Variance = 0.083 (high uncertainty)

The first few observations will move the belief dramatically. After more data, new observations have diminishing impact.

### Sampling from Beta(1,1)

When you sample from Beta(1, 1), you get uniformly random values:

```python
import random

samples = [random.betavariate(1, 1) for _ in range(1000)]
print(f"Mean of 1000 samples: {np.mean(samples):.3f}")  # ≈ 0.5
print(f"Std of 1000 samples: {np.std(samples):.3f}")   # ≈ 0.29

# Visualize
plt.figure(figsize=(10, 4))
plt.hist(samples, bins=50, density=True, alpha=0.7, edgecolor='black')
plt.axhline(1.0, color='red', linestyle='--', label='True PDF (uniform)')
plt.xlabel('Sample value')
plt.ylabel('Density')
plt.title('1000 Samples from Beta(1, 1)')
plt.legend()
plt.savefig('beta11_samples.png', dpi=150)
plt.show()
```

---

## How Data Narrows the Distribution

### The Learning Process

As observations accumulate:
- **Mean shifts** toward observed rate
- **Variance decreases** (more confident)
- **Distribution narrows** (belief concentrates)

```python
def learning_progression():
    """Watch Beta distribution narrow with data."""
    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    x = np.linspace(0, 1, 1000)

    # Simulating a coin with true rate 0.65
    true_rate = 0.65
    random.seed(42)

    # Generate observations
    all_obs = [1 if random.random() < true_rate else 0 for _ in range(200)]

    checkpoints = [0, 5, 10, 25, 50, 100, 150, 200]

    for ax, n in zip(axes.flat, checkpoints):
        obs = all_obs[:n]
        alpha = 1 + sum(obs)  # Prior (1,1) + successes
        beta = 1 + (len(obs) - sum(obs))  # Prior + failures

        pdf = stats.beta.pdf(x, alpha, beta)
        ax.plot(x, pdf, 'steelblue', linewidth=2)
        ax.fill_between(x, pdf, alpha=0.3)

        # Mark true rate
        ax.axvline(true_rate, color='green', linestyle=':', linewidth=2, label='True rate')
        # Mark current mean
        mean = alpha / (alpha + beta)
        ax.axvline(mean, color='red', linestyle='--', linewidth=1.5, label=f'Mean: {mean:.2f}')

        successes = sum(obs)
        ax.set_title(f'n={n} ({successes}W, {n-successes}L)\nBeta({alpha}, {beta})', fontsize=10)
        ax.set_xlim(0, 1)
        ax.set_xlabel('p')

        if n == 0:
            ax.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig('learning_progression.png', dpi=150)
    plt.show()

learning_progression()
```

### Convergence Rate

How fast do we learn?

```python
def convergence_analysis():
    """Analyze how variance decreases with observations."""
    ns = list(range(1, 201))
    true_rate = 0.65

    # Track mean error and variance over time
    mean_errors = []
    variances = []
    ci_widths = []

    random.seed(42)
    alpha, beta = 1, 1  # Start uniform

    for i, n in enumerate(ns):
        # Observe one outcome
        if i > 0:
            obs = 1 if random.random() < true_rate else 0
            alpha += obs
            beta += (1 - obs)

        mean = alpha / (alpha + beta)
        var = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))

        # 95% CI width (approximate)
        ci_width = 4 * np.sqrt(var)  # ~2 std each side

        mean_errors.append(abs(mean - true_rate))
        variances.append(var)
        ci_widths.append(ci_width)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    ax = axes[0]
    ax.plot(ns, mean_errors, 'steelblue', linewidth=1.5)
    ax.set_xlabel('Observations')
    ax.set_ylabel('|Mean - True Rate|')
    ax.set_title('Mean Error Over Time')
    ax.set_yscale('log')

    ax = axes[1]
    ax.plot(ns, variances, 'steelblue', linewidth=1.5)
    ax.set_xlabel('Observations')
    ax.set_ylabel('Variance')
    ax.set_title('Variance Decreases as O(1/n)')
    ax.set_yscale('log')

    ax = axes[2]
    ax.plot(ns, ci_widths, 'steelblue', linewidth=1.5)
    ax.set_xlabel('Observations')
    ax.set_ylabel('CI Width')
    ax.set_title('Confidence Interval Narrows')

    plt.tight_layout()
    plt.savefig('convergence.png', dpi=150)
    plt.show()

convergence_analysis()
```

**Key insight:** Variance decreases as O(1/n). After 100 observations, you're 10x more confident than after 10.

---

## The Math: Mean and Variance

### Mean (Expected Value)

For Beta(α, β):

```
E[X] = α / (α + β)
```

**Intuition:** The mean is the proportion of pseudo-successes.

| α | β | Mean | Interpretation |
|---|---|------|----------------|
| 1 | 1 | 0.50 | No idea |
| 3 | 1 | 0.75 | 3 successes, 1 failure → 75% |
| 10 | 10 | 0.50 | Confident about 50% |
| 7 | 3 | 0.70 | 7 successes, 3 failures → 70% |

### Variance (Uncertainty)

```
Var[X] = αβ / ((α + β)² × (α + β + 1))
```

**Intuition:** Variance depends on:
- **How balanced** (αβ is largest when α ≈ β)
- **How much data** (large α + β → small variance)

```python
def variance_heatmap():
    """Visualize how variance depends on α and β."""
    alphas = np.linspace(1, 50, 100)
    betas = np.linspace(1, 50, 100)
    A, B = np.meshgrid(alphas, betas)

    # Compute variance
    V = (A * B) / ((A + B) ** 2 * (A + B + 1))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Variance heatmap
    ax = axes[0]
    c = ax.contourf(A, B, V, levels=50, cmap='viridis')
    plt.colorbar(c, ax=ax, label='Variance')
    ax.set_xlabel('α')
    ax.set_ylabel('β')
    ax.set_title('Variance as Function of α, β\n(Darker = Lower Variance = More Confident)')

    # Variance at constant mean
    ax = axes[1]
    mean = 0.6
    total_counts = np.array([2, 5, 10, 20, 50, 100, 200])
    for total in total_counts:
        alpha = mean * total
        beta = (1 - mean) * total
        var = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
        ax.scatter(total, var, s=100)
        ax.annotate(f'({alpha:.0f},{beta:.0f})', (total, var), textcoords="offset points", xytext=(5,5))

    ax.set_xlabel('α + β (Total Pseudo-Count)')
    ax.set_ylabel('Variance')
    ax.set_title(f'Variance at Constant Mean = {mean}\nMore data → Less variance')
    ax.set_yscale('log')

    plt.tight_layout()
    plt.savefig('variance_analysis.png', dpi=150)
    plt.show()

variance_heatmap()
```

### Confidence Interval

The interval containing X% of probability mass:

```python
from scipy import stats

def compute_ci(alpha, beta, level=0.95):
    """Compute credible interval for Beta(alpha, beta)."""
    tail = (1 - level) / 2
    lower = stats.beta.ppf(tail, alpha, beta)
    upper = stats.beta.ppf(1 - tail, alpha, beta)
    return lower, upper

# Examples
examples = [(1, 1), (5, 5), (10, 10), (50, 50), (6, 4), (60, 40)]
print("95% Credible Intervals:")
print("-" * 50)
for a, b in examples:
    lo, hi = compute_ci(a, b)
    print(f"Beta({a:2d}, {b:2d}): [{lo:.3f}, {hi:.3f}]  width={hi-lo:.3f}")
```

Output:
```
95% Credible Intervals:
--------------------------------------------------
Beta( 1,  1): [0.025, 0.975]  width=0.950
Beta( 5,  5): [0.217, 0.783]  width=0.566
Beta(10, 10): [0.292, 0.708]  width=0.416
Beta(50, 50): [0.404, 0.596]  width=0.192
Beta( 6,  4): [0.309, 0.832]  width=0.523
Beta(60, 40): [0.503, 0.695]  width=0.191
```

---

## Code Walkthrough: BetaParams

Let's examine buildlog's `BetaParams` class from `src/buildlog/core/bandit.py`:

### The Full Implementation

```python
# From src/buildlog/core/bandit.py (lines 101-224)

@dataclass
class BetaParams:
    """Parameters for a Beta distribution representing belief about a rule's effectiveness.

    The Beta distribution is parameterized by α (alpha) and β (beta):

        Beta(α, β) has mean = α / (α + β)

    Interpretation:
        - α represents "pseudo-successes" (prior + observed successes)
        - β represents "pseudo-failures" (prior + observed failures)

    With uninformative prior Beta(1, 1):
        - Uniform distribution over [0, 1]
        - Mean = 0.5 (maximum uncertainty)

    As we observe outcomes:
        - Success → α += 1 (distribution shifts right)
        - Failure → β += 1 (distribution shifts left)
        - More observations → distribution narrows (less uncertainty)

    Example evolution:
        Beta(1, 1)   → Uniform, mean=0.5, high variance
        Beta(3, 2)   → Skewed right, mean=0.6, moderate variance
        Beta(30, 20) → Peaked at 0.6, low variance (high confidence)

    Attributes:
        alpha: Pseudo-count of successes (must be > 0)
        beta: Pseudo-count of failures (must be > 0)
    """

    alpha: float = 1.0
    beta: float = 1.0
```

**Design choices:**
- **Dataclass:** Immutable-ish, auto-generated `__init__`, `__repr__`, `__eq__`
- **Default (1, 1):** Uniform prior—no assumptions
- **Float, not int:** Allows partial rewards (0.5 = half credit)

### Validation

```python
    def __post_init__(self) -> None:
        """Validate parameters."""
        if self.alpha <= 0 or self.beta <= 0:
            raise ValueError(f"Alpha and beta must be positive: α={self.alpha}, β={self.beta}")
```

**Why validate?**
- Beta(0, x) or Beta(x, 0) is degenerate (point mass at 0 or 1)
- Negative values are meaningless
- Catch bugs early with clear error messages

### The Core: Sampling

```python
    def sample(self) -> float:
        """Draw a random sample from Beta(α, β).

        This is the core of Thompson Sampling: we sample from our belief
        distribution rather than using the mean. This naturally balances
        exploration (high variance → occasional high samples) and
        exploitation (high mean → consistently high samples).

        Returns:
            A value in [0, 1] representing a possible true reward rate.
        """
        return random.betavariate(self.alpha, self.beta)
```

**This is the magic.**

Instead of selecting the arm with highest mean (greedy), Thompson Sampling samples from each arm's distribution and picks the highest sample. This single line enables intelligent exploration.

### The Update

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

**Why this works:**
- Conjugate prior: posterior has same form as prior
- No normalization needed
- O(1) time, exact inference

**Partial rewards:**
- `reward=0.7` → α += 0.7, β += 0.3
- Treats as "70% success, 30% failure"
- Useful for continuous feedback signals

### Statistics

```python
    def mean(self) -> float:
        """Expected value of the distribution."""
        return self.alpha / (self.alpha + self.beta)

    def variance(self) -> float:
        """Variance of the distribution."""
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total * total * (total + 1))
```

**Usage:**
- `mean()`: For reporting, debugging, not for selection
- `variance()`: Measures uncertainty, useful for diagnostics

### Confidence Interval

```python
    def confidence_interval(self, level: float = 0.95) -> tuple[float, float]:
        """Approximate confidence interval using normal approximation."""
        import math

        mean = self.mean()
        std = math.sqrt(self.variance())
        z = 1.96 if level == 0.95 else 2.576 if level == 0.99 else 1.645

        lower = max(0.0, mean - z * std)
        upper = min(1.0, mean + z * std)
        return (lower, upper)
```

**Note:** This uses normal approximation. For exact intervals, use `scipy.stats.beta.ppf()`. The approximation is good when α + β > 10.

### Serialization

```python
    def to_dict(self) -> dict[str, float]:
        """Serialize for storage."""
        return {"alpha": self.alpha, "beta": self.beta}

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> BetaParams:
        """Deserialize from storage."""
        return cls(alpha=data["alpha"], beta=data["beta"])
```

**Why needed:**
- Persist to JSONL file
- Survive server restarts
- Enable debugging/inspection

---

## Interactive Examples

### Example 1: Two Rules, Different Histories

```python
from dataclasses import dataclass
import random

@dataclass
class BetaParams:
    alpha: float = 1.0
    beta: float = 1.0

    def sample(self) -> float:
        return random.betavariate(self.alpha, self.beta)

    def update(self, reward: float) -> None:
        self.alpha += reward
        self.beta += (1.0 - reward)

    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)


# Rule A: Tried 5 times, 4 successes (observed rate 80%)
rule_a = BetaParams(alpha=1+4, beta=1+1)  # Beta(5, 2)

# Rule B: Tried 50 times, 35 successes (observed rate 70%)
rule_b = BetaParams(alpha=1+35, beta=1+15)  # Beta(36, 16)

print(f"Rule A: Beta({rule_a.alpha:.0f}, {rule_a.beta:.0f}), mean={rule_a.mean():.2f}")
print(f"Rule B: Beta({rule_b.alpha:.0f}, {rule_b.beta:.0f}), mean={rule_b.mean():.2f}")

# Who looks better?
print(f"\nRule A has higher observed rate ({rule_a.mean():.0%} vs {rule_b.mean():.0%})")
print("But we're much less certain about A...")

# Sample 10 times from each
print("\n10 Thompson samples:")
print(f"Rule A: {[f'{rule_a.sample():.2f}' for _ in range(10)]}")
print(f"Rule B: {[f'{rule_b.sample():.2f}' for _ in range(10)]}")
```

Output:
```
Rule A: Beta(5, 2), mean=0.71
Rule B: Beta(36, 16), mean=0.69

Rule A has higher observed rate (71% vs 69%)
But we're much less certain about A...

10 Thompson samples:
Rule A: ['0.82', '0.54', '0.77', '0.63', '0.89', '0.71', '0.48', '0.81', '0.67', '0.74']
Rule B: ['0.72', '0.68', '0.71', '0.65', '0.73', '0.70', '0.67', '0.72', '0.69', '0.71']
```

**Observation:** Rule A samples vary wildly (0.48 to 0.89). Rule B samples cluster tightly (0.65 to 0.73). Thompson Sampling will sometimes explore A (when it samples high) but mostly exploit B (consistently good).

### Example 2: Watch Learning in Action

```python
def simulate_learning(true_rate, n_rounds=50, seed=42):
    """Simulate learning about a rule's effectiveness."""
    random.seed(seed)

    params = BetaParams()  # Start uniform
    history = [(params.alpha, params.beta, params.mean())]

    for _ in range(n_rounds):
        # Observe outcome
        reward = 1 if random.random() < true_rate else 0
        params.update(reward)
        history.append((params.alpha, params.beta, params.mean()))

    return history


# True rate is 0.65
history = simulate_learning(true_rate=0.65)

# Print evolution
print("Round | α    | β    | Mean")
print("-" * 30)
for i in [0, 5, 10, 20, 50]:
    a, b, m = history[i]
    print(f"{i:5d} | {a:4.1f} | {b:4.1f} | {m:.3f}")
```

Output:
```
Round | α    | β    | Mean
------------------------------
    0 |  1.0 |  1.0 | 0.500
    5 |  5.0 |  2.0 | 0.714
   10 |  8.0 |  4.0 | 0.667
   20 | 15.0 |  7.0 | 0.682
   50 | 35.0 | 17.0 | 0.673
```

The mean converges toward 0.65, and uncertainty (not shown) decreases.

---

## Exercises

### Conceptual Exercises

**Exercise 1.1: Parameter Interpretation**

For each Beta distribution, describe what you believe about the true rate:

1. Beta(20, 20)
2. Beta(100, 1)
3. Beta(2, 8)
4. Beta(1, 1000)

<details>
<summary>Solution</summary>

1. **Beta(20, 20):** "I'm fairly confident the rate is around 50%." (Mean=0.5, moderate variance)

2. **Beta(100, 1):** "I'm extremely confident the rate is very high, near 99%." (Mean≈0.99, low variance)

3. **Beta(2, 8):** "I think the rate is low, around 20%, but I'm not super confident." (Mean=0.2, moderate variance)

4. **Beta(1, 1000):** "I'm extremely confident the rate is essentially 0." (Mean≈0.001, very low variance)

</details>

---

**Exercise 1.2: Comparing Beliefs**

Two analysts have different beliefs about a rule's effectiveness:
- Alice: Beta(6, 4) — "I've seen 5 successes and 3 failures"
- Bob: Beta(60, 40) — "I've seen 59 successes and 39 failures"

Both have mean = 0.6. What's the difference between their beliefs?

<details>
<summary>Solution</summary>

Both believe the mean is 60%, but:
- **Alice** is uncertain. Her 95% CI is roughly [0.30, 0.85].
- **Bob** is confident. His 95% CI is roughly [0.50, 0.70].

Bob has seen 10x more data, so his distribution is much narrower. If new evidence suggests the rate is actually 0.8, Alice would quickly update; Bob would be slower to change his belief.

</details>

---

**Exercise 1.3: Prior Selection**

You're modeling click-through rate for a new ad. What prior would you use and why?

Options:
- Beta(1, 1)
- Beta(1, 50)
- Beta(5, 5)
- Beta(0.5, 0.5)

<details>
<summary>Solution</summary>

**Beta(1, 50)** is a reasonable choice.

Rationale:
- Click-through rates are typically low (1-5%)
- Beta(1, 50) has mean ≈ 2%, reflecting this domain knowledge
- It's still fairly weak (total pseudo-count = 51), so data will override it

Beta(1, 1) would work but ignores domain knowledge. Beta(5, 5) wrongly centers at 50%.

</details>

---

### Coding Exercises

**Exercise 1.4: Implement Mode**

Add a `mode()` method to BetaParams that returns the most likely value.

For Beta(α, β), the mode is:
- (α - 1) / (α + β - 2) when α > 1 and β > 1
- 0 when α ≤ 1 and β > 1
- 1 when α > 1 and β ≤ 1
- Undefined (bimodal) when α < 1 and β < 1

```python
def mode(self) -> float | None:
    """Return the mode (most likely value) of the distribution."""
    # YOUR CODE HERE
    pass
```

<details>
<summary>Solution</summary>

```python
def mode(self) -> float | None:
    """Return the mode (most likely value) of the distribution."""
    if self.alpha > 1 and self.beta > 1:
        return (self.alpha - 1) / (self.alpha + self.beta - 2)
    elif self.alpha <= 1 and self.beta > 1:
        return 0.0
    elif self.alpha > 1 and self.beta <= 1:
        return 1.0
    else:
        # Bimodal (U-shaped), no unique mode
        return None
```

</details>

---

**Exercise 1.5: Visualize Credible Intervals**

Write a function that plots Beta distributions with shaded 95% credible intervals.

```python
def plot_with_ci(alpha, beta, ax=None):
    """Plot Beta distribution with 95% CI shaded."""
    # YOUR CODE HERE
    pass

# Test
fig, axes = plt.subplots(1, 3, figsize=(14, 4))
for ax, (a, b) in zip(axes, [(5, 5), (30, 20), (3, 10)]):
    plot_with_ci(a, b, ax)
plt.tight_layout()
plt.savefig('ci_visualization.png', dpi=150)
plt.show()
```

<details>
<summary>Solution</summary>

```python
def plot_with_ci(alpha, beta, ax=None):
    if ax is None:
        fig, ax = plt.subplots()

    x = np.linspace(0, 1, 1000)
    pdf = stats.beta.pdf(x, alpha, beta)

    # Compute 95% CI
    lower = stats.beta.ppf(0.025, alpha, beta)
    upper = stats.beta.ppf(0.975, alpha, beta)

    # Plot PDF
    ax.plot(x, pdf, 'steelblue', linewidth=2)

    # Shade CI region
    mask = (x >= lower) & (x <= upper)
    ax.fill_between(x[mask], pdf[mask], alpha=0.4, color='steelblue', label='95% CI')

    # Mark bounds
    ax.axvline(lower, color='red', linestyle='--', alpha=0.7)
    ax.axvline(upper, color='red', linestyle='--', alpha=0.7)

    mean = alpha / (alpha + beta)
    ax.axvline(mean, color='green', linestyle='-', linewidth=2, label=f'Mean={mean:.2f}')

    ax.set_title(f'Beta({alpha}, {beta})\n95% CI: [{lower:.2f}, {upper:.2f}]')
    ax.set_xlabel('p')
    ax.legend(fontsize=8)
    ax.set_xlim(0, 1)
```

</details>

---

**Exercise 1.6: Prior Sensitivity Analysis**

How much does the prior matter? Simulate learning with different priors and compare how quickly they converge.

```python
def prior_sensitivity(true_rate, priors, n_rounds=100, n_sims=100):
    """
    For each prior, simulate n_sims learning trajectories.
    Return mean absolute error at each round.
    """
    # YOUR CODE HERE
    pass

priors = {
    'Uniform (1,1)': (1, 1),
    'Skeptical (1,5)': (1, 5),
    'Optimistic (5,1)': (5, 1),
    'Strong Wrong (1,20)': (1, 20),
}

# True rate is 0.6
results = prior_sensitivity(0.6, priors)
# Plot convergence curves
```

<details>
<summary>Solution</summary>

```python
def prior_sensitivity(true_rate, priors, n_rounds=100, n_sims=100):
    results = {}

    for name, (a0, b0) in priors.items():
        errors = np.zeros(n_rounds + 1)

        for _ in range(n_sims):
            alpha, beta = a0, b0
            for t in range(n_rounds + 1):
                mean = alpha / (alpha + beta)
                errors[t] += abs(mean - true_rate)

                if t < n_rounds:
                    reward = 1 if random.random() < true_rate else 0
                    alpha += reward
                    beta += (1 - reward)

        results[name] = errors / n_sims

    return results

# Plot
plt.figure(figsize=(10, 6))
for name, errors in results.items():
    plt.plot(errors, label=name, linewidth=2)
plt.xlabel('Observations')
plt.ylabel('Mean Absolute Error')
plt.title('Prior Sensitivity: How Fast Do Different Priors Converge?')
plt.legend()
plt.yscale('log')
plt.savefig('prior_sensitivity.png', dpi=150)
plt.show()
```

**Key insight:** Even "wrong" priors converge eventually. The prior matters most early on, but data dominates after ~20-50 observations.

</details>

---

### Challenge Exercises

**Exercise 1.7: Quantile Function**

Implement the inverse CDF (quantile function) for Beta using binary search.

```python
def beta_quantile(alpha, beta, p, tol=1e-6):
    """
    Find x such that P(X <= x) = p for X ~ Beta(alpha, beta).
    Use binary search since we can evaluate the CDF.
    """
    # YOUR CODE HERE
    pass

# Test against scipy
from scipy import stats
for p in [0.05, 0.5, 0.95]:
    mine = beta_quantile(5, 3, p)
    scipy = stats.beta.ppf(p, 5, 3)
    print(f"p={p}: mine={mine:.6f}, scipy={scipy:.6f}")
```

<details>
<summary>Solution</summary>

```python
def beta_quantile(alpha, beta, p, tol=1e-6):
    from scipy import stats as sp_stats

    lo, hi = 0.0, 1.0
    while hi - lo > tol:
        mid = (lo + hi) / 2
        cdf = sp_stats.beta.cdf(mid, alpha, beta)
        if cdf < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
```

</details>

---

**Exercise 1.8: Bayesian A/B Testing**

Two variants of a button:
- A: 45 clicks out of 500 views (9%)
- B: 55 clicks out of 500 views (11%)

Calculate P(B is better than A) by Monte Carlo sampling.

```python
def prob_b_better(a_successes, a_trials, b_successes, b_trials, n_samples=100000):
    """
    Estimate P(rate_B > rate_A) by sampling from posteriors.
    """
    # YOUR CODE HERE
    pass

prob = prob_b_better(45, 500, 55, 500)
print(f"P(B > A) = {prob:.1%}")
```

<details>
<summary>Solution</summary>

```python
def prob_b_better(a_successes, a_trials, b_successes, b_trials, n_samples=100000):
    # Posteriors with Beta(1,1) prior
    a_alpha = 1 + a_successes
    a_beta = 1 + (a_trials - a_successes)
    b_alpha = 1 + b_successes
    b_beta = 1 + (b_trials - b_successes)

    count_b_better = 0
    for _ in range(n_samples):
        sample_a = random.betavariate(a_alpha, a_beta)
        sample_b = random.betavariate(b_alpha, b_beta)
        if sample_b > sample_a:
            count_b_better += 1

    return count_b_better / n_samples

# Result: ~92% probability that B is better than A
```

</details>

---

**Exercise 1.9: Implement Jeffreys Prior Update**

The Jeffreys prior is Beta(0.5, 0.5)—it's "uninformative" in a technical sense (invariant under reparameterization).

Modify BetaParams to support different priors, and compare how Jeffreys vs Uniform priors behave with small samples.

<details>
<summary>Hint</summary>

```python
class BetaParamsWithPrior:
    def __init__(self, prior_alpha=1.0, prior_beta=1.0):
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta
        self.successes = 0
        self.failures = 0

    @property
    def alpha(self):
        return self.prior_alpha + self.successes

    # ... etc
```

With Jeffreys prior, after 0 observations, sampling can return values close to 0 or 1. With uniform prior, samples spread evenly.

</details>

---

## Summary

You now understand:

1. **Why Beta:** It's designed for probabilities in [0, 1] with conjugate updates
2. **Parameters:** α = pseudo-successes, β = pseudo-failures
3. **Shapes:** Symmetric when α = β, skewed otherwise, narrow with large α + β
4. **Uniform prior:** Beta(1, 1) expresses maximum uncertainty
5. **Convergence:** Variance decreases as O(1/n), data dominates prior
6. **BetaParams:** buildlog's implementation is simple, correct, and well-documented

In **Tutorial 2**, we'll dive into Bayesian updates—the mechanics of learning from feedback.

---

*Previous: [Tutorial 0: Background Concepts](./00-background-concepts.md)*

*Next: [Tutorial 2: Bayesian Updates](./02-bayesian-updates.md)*
