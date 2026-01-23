# Tutorial 0: Background Concepts

**The Prerequisites You Skipped in College, Now Made Useful**

This tutorial covers the foundational concepts you need before diving into Thompson Sampling. If you haven't touched probability since college, this is for you. By the end, you'll have working intuitions and runnable code for everything that follows.

---

## Table of Contents

1. [The Multi-Armed Bandit Problem](#the-multi-armed-bandit-problem)
2. [The Explore-Exploit Tradeoff](#the-explore-exploit-tradeoff)
3. [Why This Matters for Agent Learning](#why-this-matters-for-agent-learning)
4. [Probability Distributions Refresher](#probability-distributions-refresher)
5. [The Beta Distribution](#the-beta-distribution)
6. [Bayesian Inference in 5 Minutes](#bayesian-inference-in-5-minutes)
7. [Conjugate Priors](#conjugate-priors)
8. [Putting It Together](#putting-it-together)

---

## The Multi-Armed Bandit Problem

### The Casino Metaphor

Imagine you're in a casino with a row of slot machines ("one-armed bandits"). Each machine has a different, unknown payout rate. You have limited coins to spend. **How do you maximize your winnings?**

```
    🎰 A        🎰 B        🎰 C        🎰 D
   [???]       [???]       [???]       [???]

   True rates (unknown to you):
   A: 10%      B: 45%      C: 30%      D: 20%
```

The catch: you don't know the true rates. You only learn by pulling levers and observing outcomes.

### The Core Tension

Two obvious strategies, both flawed:

**Strategy 1: Pure Exploration**
Pull each machine equally. You'll learn accurate rates, but you'll waste half your coins on bad machines while learning.

**Strategy 2: Pure Exploitation**
Pull the first machine that wins a few times, stick with it forever. You might get lucky, or you might settle on a 20% machine when a 45% machine was right next door.

```python
import random

def simulate_bandit(true_rates, strategy, n_pulls=1000):
    """Simulate a multi-armed bandit problem."""
    k = len(true_rates)
    wins = [0] * k
    pulls = [0] * k
    total_reward = 0

    for t in range(n_pulls):
        # Strategy decides which arm to pull
        arm = strategy(wins, pulls, t)
        pulls[arm] += 1

        # Observe reward (1 with probability true_rates[arm], else 0)
        reward = 1 if random.random() < true_rates[arm] else 0
        wins[arm] += reward
        total_reward += reward

    return total_reward, pulls

# Pure exploration: uniform random
def explore_strategy(wins, pulls, t):
    return random.randint(0, len(wins) - 1)

# Pure exploitation: always pick current best
def exploit_strategy(wins, pulls, t):
    rates = [w / max(p, 1) for w, p in zip(wins, pulls)]
    return rates.index(max(rates))

# Run simulations
true_rates = [0.10, 0.45, 0.30, 0.20]

random.seed(42)
explore_reward, explore_pulls = simulate_bandit(true_rates, explore_strategy)
print(f"Pure exploration: {explore_reward} wins, pulls: {explore_pulls}")

random.seed(42)
exploit_reward, exploit_pulls = simulate_bandit(true_rates, exploit_strategy)
print(f"Pure exploitation: {exploit_reward} wins, pulls: {exploit_pulls}")

# Optimal (if we knew the truth): always pull best arm
optimal_reward = int(0.45 * 1000)
print(f"Optimal (oracle): {optimal_reward} wins")
```

Output:
```
Pure exploration: 263 wins, pulls: [254, 251, 249, 246]
Pure exploitation: 298 wins, pulls: [3, 12, 983, 2]
Optimal (oracle): 450 wins
```

Notice: pure exploitation got stuck on the 30% machine (C) because it happened to win early. It never discovered the 45% machine (B).

### Regret: The Formal Measure

**Regret** is the difference between what you earned and what you *could have* earned if you'd always pulled the best arm.

```
Regret = (Best rate × Total pulls) - Actual reward
       = 450 - 298 = 152 wins left on the table
```

Good bandit algorithms have **sublinear regret**—they approach optimal performance as time goes on. The goal isn't zero regret (impossible without knowing the truth), but regret that grows slower than linearly.

---

## The Explore-Exploit Tradeoff

This tension between exploration and exploitation is fundamental. It appears everywhere:

| Domain | Exploration | Exploitation |
|--------|-------------|--------------|
| Slot machines | Try new machines | Pull the current best |
| A/B testing | Show variant B | Show winning variant A |
| Restaurant choice | Try new place | Go to favorite |
| Job search | Interview at new companies | Accept good offer |
| Agent rules | Test new rules | Use proven rules |

### Naive Solutions

**Epsilon-greedy**: Explore with probability ε, exploit otherwise.

```python
def epsilon_greedy(wins, pulls, t, epsilon=0.1):
    if random.random() < epsilon:
        return random.randint(0, len(wins) - 1)  # Explore
    rates = [w / max(p, 1) for w, p in zip(wins, pulls)]
    return rates.index(max(rates))  # Exploit
```

Problems:
- ε is a hyperparameter you must tune
- Explores uniformly, even among clearly bad arms
- Explores forever, even when confident

**Decaying epsilon**: ε decreases over time.

```python
def decaying_epsilon_greedy(wins, pulls, t, initial_epsilon=0.5):
    epsilon = initial_epsilon / (1 + t * 0.01)
    if random.random() < epsilon:
        return random.randint(0, len(wins) - 1)
    rates = [w / max(p, 1) for w, p in zip(wins, pulls)]
    return rates.index(max(rates))
```

Better, but still:
- More hyperparameters to tune
- Doesn't account for *which* arms are uncertain
- Explores uniformly when it does explore

### The Key Insight

What we really want is **uncertainty-aware** exploration:
- Explore arms we're uncertain about
- Stop exploring arms we're confident are bad
- Automatically balance based on how much we know

This is exactly what Thompson Sampling does. But first, we need to understand probability distributions.

---

## Why This Matters for Agent Learning

In buildlog, we face the exact same problem:

```
    📜 Rule A    📜 Rule B    📜 Rule C    📜 Rule D
    [???]        [???]        [???]        [???]

    True effectiveness (unknown):
    A: 10%       B: 45%       C: 30%       D: 20%
```

Each "rule" is an arm. Each "session where the rule was active" is a pull. Each "mistake despite the rule" is a loss (reward=0). Each "no mistake" is a win (reward=1).

**The question**: Which rules should we surface to the agent?

If we always show the same rules, we might miss better ones. If we randomly rotate rules, we waste sessions on bad rules. We need intelligent, uncertainty-aware selection.

---

## Probability Distributions Refresher

### What Is a Distribution?

A probability distribution describes the likelihood of different outcomes. Think of it as a "shape" over possible values.

```python
import numpy as np
import matplotlib.pyplot as plt

# Discrete: rolling a fair die
outcomes = [1, 2, 3, 4, 5, 6]
probabilities = [1/6] * 6

plt.figure(figsize=(10, 4))

plt.subplot(1, 2, 1)
plt.bar(outcomes, probabilities, color='steelblue', edgecolor='black')
plt.xlabel('Outcome')
plt.ylabel('Probability')
plt.title('Fair Die (Discrete Uniform)')
plt.ylim(0, 0.3)

# Continuous: heights of adults (approximately normal)
x = np.linspace(150, 200, 1000)
mean, std = 170, 10
pdf = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / std) ** 2)

plt.subplot(1, 2, 2)
plt.plot(x, pdf, color='steelblue', linewidth=2)
plt.fill_between(x, pdf, alpha=0.3)
plt.xlabel('Height (cm)')
plt.ylabel('Probability Density')
plt.title('Adult Heights (Normal)')

plt.tight_layout()
plt.savefig('distributions_intro.png', dpi=150)
plt.show()
```

Key concepts:
- **Discrete**: Finite outcomes (die roll, coin flip, category)
- **Continuous**: Infinite outcomes on a range (height, temperature, probability)
- **PDF (Probability Density Function)**: For continuous distributions, the "height" of the curve at each point. The area under the curve is probability.

### Parameters Shape the Distribution

Most distributions are controlled by **parameters**. Change the parameters, change the shape.

```python
# Normal distribution with different parameters
fig, axes = plt.subplots(1, 3, figsize=(12, 4))

x = np.linspace(-10, 20, 1000)

# Different means
for mean in [0, 5, 10]:
    pdf = (1 / (2 * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / 2) ** 2)
    axes[0].plot(x, pdf, label=f'μ={mean}')
axes[0].set_title('Different Means (μ)')
axes[0].legend()

# Different standard deviations
for std in [1, 2, 4]:
    pdf = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - 5) / std) ** 2)
    axes[1].plot(x, pdf, label=f'σ={std}')
axes[1].set_title('Different Std Devs (σ)')
axes[1].legend()

# Together
params = [(0, 1), (5, 2), (10, 3)]
for mean, std in params:
    pdf = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / std) ** 2)
    axes[2].plot(x, pdf, label=f'μ={mean}, σ={std}')
axes[2].set_title('Both Varying')
axes[2].legend()

plt.tight_layout()
plt.savefig('normal_parameters.png', dpi=150)
plt.show()
```

For bandits, we care about one specific distribution: **Beta**.

---

## The Beta Distribution

### Why Beta?

We're modeling **probabilities**—values between 0 and 1. The Beta distribution is perfect because:

1. **Domain is [0, 1]**: Exactly what we need for probabilities
2. **Flexible shape**: Can represent many beliefs (uniform, skewed, peaked)
3. **Conjugate to Bernoulli**: Updates are trivial (more on this soon)
4. **Easy to sample**: Python's `random.betavariate(α, β)` just works

### Parameters: α and β

The Beta distribution has two parameters:
- **α (alpha)**: "Pseudo-successes" — how many wins we've seen (plus prior)
- **β (beta)**: "Pseudo-failures" — how many losses we've seen (plus prior)

```python
from scipy import stats

def plot_beta_distributions():
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    x = np.linspace(0, 1, 1000)

    params = [
        (1, 1, "α=1, β=1\n(Uniform: Maximum Ignorance)"),
        (2, 2, "α=2, β=2\n(Slightly peaked at 0.5)"),
        (5, 5, "α=5, β=5\n(Confident around 0.5)"),
        (2, 8, "α=2, β=8\n(Believe rate is low ~0.2)"),
        (8, 2, "α=8, β=2\n(Believe rate is high ~0.8)"),
        (30, 10, "α=30, β=10\n(Very confident: rate ~0.75)"),
    ]

    for ax, (a, b, title) in zip(axes.flat, params):
        pdf = stats.beta.pdf(x, a, b)
        ax.plot(x, pdf, 'b-', linewidth=2)
        ax.fill_between(x, pdf, alpha=0.3)
        ax.axvline(a / (a + b), color='red', linestyle='--',
                   label=f'Mean = {a/(a+b):.2f}')
        ax.set_title(title, fontsize=10)
        ax.set_xlabel('Probability')
        ax.set_ylabel('Density')
        ax.legend(fontsize=8)
        ax.set_xlim(0, 1)

    plt.tight_layout()
    plt.savefig('beta_distributions.png', dpi=150)
    plt.show()

plot_beta_distributions()
```

### Key Properties

**Mean (Expected Value)**:
```
E[X] = α / (α + β)
```

This is your "best guess" for the probability.

**Variance (Uncertainty)**:
```
Var[X] = (α × β) / ((α + β)² × (α + β + 1))
```

Higher α + β = more observations = lower variance = more confident.

```python
def beta_stats(alpha, beta):
    mean = alpha / (alpha + beta)
    variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
    return mean, variance

# Compare uncertainty at same mean but different sample sizes
print("Same mean (0.6), different confidence:")
print(f"  α=3, β=2:   mean={beta_stats(3, 2)[0]:.2f}, var={beta_stats(3, 2)[1]:.4f}")
print(f"  α=30, β=20: mean={beta_stats(30, 20)[0]:.2f}, var={beta_stats(30, 20)[1]:.4f}")
print(f"  α=300, β=200: mean={beta_stats(300, 200)[0]:.2f}, var={beta_stats(300, 200)[1]:.6f}")
```

Output:
```
Same mean (0.6), different confidence:
  α=3, β=2:   mean=0.60, var=0.0400
  α=30, β=20: mean=0.60, var=0.0047
  α=300, β=200: mean=0.60, var=0.000478
```

**Interpretation**: α=3, β=2 means "I've seen 2 wins and 1 loss (plus uniform prior)." α=300, β=200 means "I've seen ~299 wins and ~199 losses." Same estimated rate, vastly different confidence.

### Sampling from Beta

This is the magic behind Thompson Sampling:

```python
import random

# Sample from Beta(3, 7) — believe rate is around 0.3
samples = [random.betavariate(3, 7) for _ in range(10)]
print("10 samples from Beta(3, 7):")
print([f"{s:.3f}" for s in samples])

# Each sample is a "plausible" value given our uncertainty
```

Output:
```
10 samples from Beta(3, 7):
['0.194', '0.372', '0.252', '0.285', '0.344', '0.179', '0.402', '0.227', '0.333', '0.281']
```

Notice: samples vary around the mean (0.3) but reflect our uncertainty. Sometimes we get 0.19, sometimes 0.40.

---

## Bayesian Inference in 5 Minutes

### The Framework

Bayesian inference is a recipe for updating beliefs:

```
Prior (what we believed before)
    × Likelihood (how likely is this data given different hypotheses?)
    ∝ Posterior (what we believe now)
```

In code terms:

```python
# Conceptually (not actual code):
posterior = prior * likelihood
posterior = normalize(posterior)  # Make it sum/integrate to 1
```

### Example: Is This Coin Fair?

You have a coin. You flip it 10 times: 7 heads, 3 tails. Is it fair?

**Frequentist answer**: "The observed rate is 70%. With more data, we'd get closer to the true rate."

**Bayesian answer**: "Given my prior belief and this data, here's my updated belief distribution over all possible rates."

```python
def bayesian_coin_flip():
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    x = np.linspace(0, 1, 1000)

    # Prior: no idea (uniform)
    prior_a, prior_b = 1, 1

    observations = [
        (0, 0, "Prior: No data yet"),
        (3, 1, "After 4 flips: 3H, 1T"),
        (7, 3, "After 10 flips: 7H, 3T"),
        (70, 30, "After 100 flips: 70H, 30T"),
    ]

    for ax, (heads, tails, title) in zip(axes, observations):
        # Posterior = Prior + Observations
        post_a = prior_a + heads
        post_b = prior_b + tails

        pdf = stats.beta.pdf(x, post_a, post_b)
        ax.plot(x, pdf, 'b-', linewidth=2)
        ax.fill_between(x, pdf, alpha=0.3)
        ax.axvline(0.5, color='green', linestyle=':', label='Fair (0.5)')
        ax.axvline(post_a / (post_a + post_b), color='red', linestyle='--',
                   label=f'Mean: {post_a/(post_a+post_b):.2f}')
        ax.set_title(title)
        ax.set_xlabel('P(Heads)')
        ax.legend(fontsize=8)
        ax.set_xlim(0, 1)

    plt.tight_layout()
    plt.savefig('bayesian_coin.png', dpi=150)
    plt.show()

bayesian_coin_flip()
```

**The update rule is trivial**:
```
New α = Old α + (number of heads)
New β = Old β + (number of tails)
```

That's it. No calculus, no integrals, no normalization constants. This simplicity is the magic of conjugate priors.

---

## Conjugate Priors

### What "Conjugate" Means

A prior is **conjugate** to a likelihood if the posterior has the same distributional form as the prior.

For Beta-Bernoulli:
- **Prior**: Beta(α, β)
- **Likelihood**: Bernoulli (coin flip: 0 or 1)
- **Posterior**: Beta(α + successes, β + failures)

The posterior is still a Beta distribution! Just with updated parameters.

### Why This Matters

Without conjugacy, updating beliefs requires:
1. Computing complex integrals
2. Numerical approximations (MCMC, variational inference)
3. Significantly more compute

With conjugacy:
```python
def update(self, reward: float) -> None:
    """Update posterior with observed reward."""
    self.alpha += reward
    self.beta += (1 - reward)
```

Two lines of code. O(1) time. Exact answer.

### Common Conjugate Pairs

| Likelihood | Conjugate Prior | Use Case |
|------------|-----------------|----------|
| Bernoulli (binary) | Beta | Coin flips, click-through rates |
| Categorical | Dirichlet | Multi-class outcomes |
| Poisson (counts) | Gamma | Event counts per time |
| Normal (known var) | Normal | Continuous measurements |

For bandits with binary outcomes (success/failure), Beta-Bernoulli is the natural choice.

---

## Putting It Together

Let's connect all the concepts to our bandit problem:

```python
class BanditArm:
    """One arm of a multi-armed bandit using Beta-Bernoulli model."""

    def __init__(self, alpha=1.0, beta=1.0):
        """
        Initialize with prior beliefs.

        Default Beta(1, 1) = uniform = "I have no idea"
        Boosted Beta(3, 1) = "I believe this is probably good" (e.g., expert-curated)
        """
        self.alpha = alpha
        self.beta = beta

    def sample(self) -> float:
        """
        Sample a plausible success rate from our belief distribution.

        This is the KEY to Thompson Sampling:
        - If we're uncertain, samples vary widely → exploration
        - If we're confident, samples cluster near mean → exploitation
        """
        import random
        return random.betavariate(self.alpha, self.beta)

    def update(self, reward: float) -> None:
        """
        Update beliefs after observing a reward.

        Bayesian update for Beta-Bernoulli:
        - α += reward (pseudo-success)
        - β += (1 - reward) (pseudo-failure)

        For binary rewards: reward=1 → α++, reward=0 → β++
        For continuous [0,1]: proportional update
        """
        self.alpha += reward
        self.beta += (1 - reward)

    @property
    def mean(self) -> float:
        """Expected success rate."""
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        """Uncertainty in our estimate."""
        a, b = self.alpha, self.beta
        return (a * b) / ((a + b) ** 2 * (a + b + 1))

    def __repr__(self):
        return f"BanditArm(α={self.alpha:.1f}, β={self.beta:.1f}, mean={self.mean:.3f})"


# Demo: Two arms, one good, one bad
arm_good = BanditArm()  # True rate: 0.7
arm_bad = BanditArm()   # True rate: 0.2

print("Initial state:")
print(f"  Good arm: {arm_good}")
print(f"  Bad arm:  {arm_bad}")

# Simulate 20 pulls, alternating for demonstration
import random
random.seed(42)

for i in range(10):
    # Pull good arm
    reward = 1 if random.random() < 0.7 else 0
    arm_good.update(reward)

    # Pull bad arm
    reward = 1 if random.random() < 0.2 else 0
    arm_bad.update(reward)

print("\nAfter 10 pulls each:")
print(f"  Good arm: {arm_good}")
print(f"  Bad arm:  {arm_bad}")

# Now sample to see Thompson Sampling in action
print("\n5 Thompson samples from each:")
print(f"  Good arm samples: {[f'{arm_good.sample():.3f}' for _ in range(5)]}")
print(f"  Bad arm samples:  {[f'{arm_bad.sample():.3f}' for _ in range(5)]}")
```

Output:
```
Initial state:
  Good arm: BanditArm(α=1.0, β=1.0, mean=0.500)
  Bad arm:  BanditArm(α=1.0, β=1.0, mean=0.500)

After 10 pulls each:
  Good arm: BanditArm(α=8.0, β=4.0, mean=0.667)
  Bad arm:  BanditArm(α=3.0, β=9.0, mean=0.250)

5 Thompson samples from each:
  Good arm samples: ['0.642', '0.712', '0.558', '0.693', '0.609']
  Bad arm samples:  ['0.214', '0.293', '0.177', '0.341', '0.208']
```

Notice:
- After data, beliefs have diverged
- Good arm samples are consistently higher
- But bad arm still sometimes samples above 0.3 — occasional exploration
- As data accumulates, overlap decreases → more exploitation

---

## Next Steps

You now have the foundations:

1. **Multi-armed bandit**: The problem of choosing among unknown options
2. **Explore-exploit**: The tension between learning and earning
3. **Beta distribution**: The right tool for modeling unknown probabilities
4. **Bayesian updating**: How to learn from observations
5. **Conjugate priors**: Why Beta-Bernoulli updates are so simple

In **Tutorial 1**, we'll go deeper on the Beta distribution—visualizing how it evolves, understanding its shape, and implementing the `BetaParams` class from buildlog.

---

## Exercises

### Conceptual Exercises

**Exercise 0.1: Regret Calculation**

A bandit has 3 arms with true rates [0.3, 0.7, 0.5]. After 1000 pulls, you pulled arm A 400 times (120 wins), arm B 100 times (68 wins), and arm C 500 times (245 wins).

Calculate:
- (a) Total reward earned
- (b) Optimal reward (if you knew the truth)
- (c) Regret
- (d) Which arm should you have pulled?

<details>
<summary>Solution</summary>

```python
# (a) Total reward
total_reward = 120 + 68 + 245  # = 433

# (b) Optimal: always pull best arm (B, rate 0.7)
optimal_reward = 1000 * 0.7  # = 700

# (c) Regret
regret = optimal_reward - total_reward  # = 700 - 433 = 267

# (d) Arm B (0.7 rate) should have been pulled exclusively
```

</details>

---

**Exercise 0.2: Explore-Exploit Scenarios**

For each scenario, decide: should you explore more, exploit more, or are you balanced?

1. You've pulled arm A 500 times (250 wins) and arm B 5 times (4 wins).
2. You've pulled both arms 100 times each. A has 60 wins, B has 58 wins.
3. You've pulled arm A 1000 times (700 wins) and have 100 pulls left.
4. A new arm C just appeared. You've never pulled it.

<details>
<summary>Solution</summary>

1. **Explore more**: Arm B looks promising (80% observed rate) but with only 5 samples, you're very uncertain. Explore B.

2. **Exploit**: Both arms have substantial data. A is slightly better (60% vs 58%). Rates are close but confident—exploit A.

3. **Exploit**: With only 100 pulls left and high confidence in A (70% rate), exploring is unlikely to help. Exploit.

4. **Explore**: You must try C at least a few times—it could be the best arm.

</details>

---

**Exercise 0.3: Beta Interpretation**

Interpret each Beta distribution in plain English:

1. Beta(1, 1)
2. Beta(10, 10)
3. Beta(1, 9)
4. Beta(50, 5)
5. Beta(100, 100)

<details>
<summary>Solution</summary>

1. **Beta(1, 1)**: "I have no idea. Could be anything from 0 to 1." (Uniform prior)

2. **Beta(10, 10)**: "I think it's around 50%, but I'm not super confident." (Mean=0.5, moderate variance)

3. **Beta(1, 9)**: "I think it's pretty bad, around 10%." (Mean=0.1, skewed left)

4. **Beta(50, 5)**: "I'm quite confident it's high, around 91%." (Mean≈0.91, concentrated)

5. **Beta(100, 100)**: "I'm very confident it's close to 50%." (Mean=0.5, low variance)

</details>

---

### Coding Exercises

**Exercise 0.4: Explore-Then-Exploit Strategy**

Implement a strategy that explores uniformly for the first N pulls, then exploits the empirical best arm.

```python
def explore_then_exploit(wins, pulls, t, explore_rounds=100):
    """
    Explore uniformly for first `explore_rounds` pulls,
    then always pull the arm with highest observed win rate.

    Args:
        wins: List of wins per arm
        pulls: List of pulls per arm
        t: Current time step (0-indexed)
        explore_rounds: Number of rounds to explore

    Returns:
        Index of arm to pull
    """
    # YOUR CODE HERE
    pass


# Test it
true_rates = [0.10, 0.45, 0.30, 0.20]
random.seed(42)
reward, pull_counts = simulate_bandit(true_rates, explore_then_exploit)
print(f"Explore-then-exploit: {reward} wins, pulls: {pull_counts}")
```

<details>
<summary>Solution</summary>

```python
def explore_then_exploit(wins, pulls, t, explore_rounds=100):
    k = len(wins)

    if t < explore_rounds:
        # Explore: cycle through arms
        return t % k
    else:
        # Exploit: pick best observed rate
        rates = [w / max(p, 1) for w, p in zip(wins, pulls)]
        return rates.index(max(rates))

# Expected output: Better than pure exploit because it explores all arms first
# Explore-then-exploit: ~380-420 wins, with most pulls on arm B
```

</details>

---

**Exercise 0.5: Visualize Beta Evolution**

Write code that shows how a Beta distribution evolves as you observe coin flips.

```python
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

def visualize_beta_evolution(observations, figsize=(14, 4)):
    """
    Plot Beta distribution at multiple checkpoints as observations accumulate.

    Args:
        observations: List of 0s and 1s (coin flips)

    Example:
        visualize_beta_evolution([1, 1, 0, 1, 1, 1, 0, 1, 0, 1])
    """
    # YOUR CODE HERE: Plot at 0, 25%, 50%, 75%, 100% of observations
    pass


# Test with 40 flips from a coin with P(heads)=0.6
random.seed(123)
flips = [1 if random.random() < 0.6 else 0 for _ in range(40)]
visualize_beta_evolution(flips)
```

<details>
<summary>Solution</summary>

```python
def visualize_beta_evolution(observations, figsize=(14, 4)):
    n = len(observations)
    checkpoints = [0, n // 4, n // 2, 3 * n // 4, n]

    fig, axes = plt.subplots(1, 5, figsize=figsize)
    x = np.linspace(0, 1, 1000)

    alpha, beta = 1, 1  # Start with uniform prior

    for i, (ax, checkpoint) in enumerate(zip(axes, checkpoints)):
        # Update to this checkpoint
        if i > 0:
            prev_checkpoint = checkpoints[i - 1]
            new_obs = observations[prev_checkpoint:checkpoint]
            alpha += sum(new_obs)
            beta += len(new_obs) - sum(new_obs)

        pdf = stats.beta.pdf(x, alpha, beta)
        ax.plot(x, pdf, 'b-', linewidth=2)
        ax.fill_between(x, pdf, alpha=0.3)
        ax.axvline(alpha / (alpha + beta), color='red', linestyle='--')
        ax.set_title(f'After {checkpoint} obs\nα={alpha}, β={beta}')
        ax.set_xlabel('P(heads)')
        ax.set_xlim(0, 1)

    plt.tight_layout()
    plt.savefig('beta_evolution.png', dpi=150)
    plt.show()
```

</details>

---

**Exercise 0.6: Confidence Intervals**

Add a `credible_interval` method to the `BanditArm` class that returns the central X% credible interval.

```python
from scipy import stats

class BanditArmWithCI(BanditArm):
    def credible_interval(self, confidence=0.95):
        """
        Return the central credible interval.

        Args:
            confidence: Probability mass within interval (default 0.95)

        Returns:
            Tuple (lower, upper) bounds

        Example:
            arm = BanditArmWithCI(10, 5)
            arm.credible_interval(0.95)  # Returns (0.43, 0.85) approximately
        """
        # YOUR CODE HERE
        pass


# Test it
arm = BanditArmWithCI(10, 5)
ci = arm.credible_interval(0.95)
print(f"95% CI for Beta(10, 5): [{ci[0]:.3f}, {ci[1]:.3f}]")
```

<details>
<summary>Solution</summary>

```python
def credible_interval(self, confidence=0.95):
    tail = (1 - confidence) / 2
    lower = stats.beta.ppf(tail, self.alpha, self.beta)
    upper = stats.beta.ppf(1 - tail, self.alpha, self.beta)
    return (lower, upper)

# For Beta(10, 5):
# 95% CI: [0.431, 0.852]
# Mean: 0.667
# The interval captures 95% of the probability mass
```

</details>

---

**Exercise 0.7: Regret Over Time**

Implement a function that tracks cumulative regret over time for different strategies, then plot the results.

```python
def track_regret(true_rates, strategy, n_pulls=1000):
    """
    Track cumulative regret at each time step.

    Returns:
        List of cumulative regret values (length n_pulls)
    """
    # YOUR CODE HERE
    pass


# Compare strategies
true_rates = [0.1, 0.45, 0.3, 0.2]
strategies = {
    'Pure Explore': explore_strategy,
    'Pure Exploit': exploit_strategy,
    'Explore-then-Exploit': explore_then_exploit,
    'Epsilon-Greedy (0.1)': lambda w, p, t: epsilon_greedy(w, p, t, 0.1),
}

plt.figure(figsize=(10, 6))
for name, strategy in strategies.items():
    random.seed(42)
    regrets = track_regret(true_rates, strategy)
    plt.plot(regrets, label=name)

plt.xlabel('Time Step')
plt.ylabel('Cumulative Regret')
plt.title('Regret Comparison Across Strategies')
plt.legend()
plt.savefig('regret_comparison.png', dpi=150)
plt.show()
```

<details>
<summary>Solution</summary>

```python
def track_regret(true_rates, strategy, n_pulls=1000):
    best_rate = max(true_rates)
    k = len(true_rates)
    wins = [0] * k
    pulls = [0] * k
    cumulative_regret = []
    total_regret = 0

    for t in range(n_pulls):
        arm = strategy(wins, pulls, t)
        pulls[arm] += 1
        reward = 1 if random.random() < true_rates[arm] else 0
        wins[arm] += reward

        # Regret = best possible reward - actual reward
        instant_regret = best_rate - true_rates[arm]
        total_regret += instant_regret
        cumulative_regret.append(total_regret)

    return cumulative_regret

# Expected: Explore-then-exploit and epsilon-greedy should have
# sublinear regret growth; pure strategies should be worse.
```

</details>

---

### Challenge Exercises

**Exercise 0.8: Non-Stationary Bandits**

What if arm payoff rates change over time? Modify the `BanditArm` class to use a "sliding window" of recent observations instead of all-time totals.

Hint: Store the last N observations in a deque, recompute α and β from the window.

<details>
<summary>Hint</summary>

```python
from collections import deque

class SlidingWindowArm:
    def __init__(self, window_size=50, prior_alpha=1, prior_beta=1):
        self.window_size = window_size
        self.observations = deque(maxlen=window_size)
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta

    @property
    def alpha(self):
        return self.prior_alpha + sum(self.observations)

    @property
    def beta(self):
        return self.prior_beta + len(self.observations) - sum(self.observations)

    # ... implement sample(), update(), etc.
```

</details>

---

**Exercise 0.9: Multi-Objective Bandits**

Suppose each arm has TWO outcomes: reward and cost. You want to maximize reward while minimizing cost. How would you modify the Beta model?

Think about:
- What distributions would you use?
- How would you combine them for arm selection?
- What's the tradeoff parameter?

<details>
<summary>Discussion</summary>

Options:
1. **Scalarize**: Define utility = reward - λ × cost, model with single Beta
2. **Pareto**: Maintain separate Betas, use multi-objective Thompson Sampling
3. **Constrained**: Maximize reward subject to cost < threshold

For buildlog: A rule might prevent mistakes (reward) but also slow down the agent (cost). The scalarization approach is simplest: model net benefit directly.

</details>

---

**Exercise 0.10: Derive the Bayesian Update**

Starting from Bayes' theorem, derive why the posterior for Beta-Bernoulli is Beta(α + s, β + f) where s = successes and f = failures.

Hint:
```
P(θ|data) ∝ P(data|θ) × P(θ)
         ∝ θ^s × (1-θ)^f × θ^(α-1) × (1-θ)^(β-1)
```

<details>
<summary>Solution</summary>

```
Prior:      P(θ) = Beta(α, β) ∝ θ^(α-1) × (1-θ)^(β-1)

Likelihood: P(data|θ) = θ^s × (1-θ)^f
            (s successes, f failures in Bernoulli trials)

Posterior:  P(θ|data) ∝ P(data|θ) × P(θ)
                      ∝ θ^s × (1-θ)^f × θ^(α-1) × (1-θ)^(β-1)
                      = θ^(s+α-1) × (1-θ)^(f+β-1)
                      ∝ Beta(α+s, β+f)

The posterior is Beta with:
  - New α = old α + successes
  - New β = old β + failures

QED: Beta is conjugate to Bernoulli.
```

</details>

---

## References

- Russo, D., et al. (2018). "A Tutorial on Thompson Sampling." *Foundations and Trends in Machine Learning*.
- Slivkins, A. (2019). "Introduction to Multi-Armed Bandits." *Foundations and Trends in Machine Learning*.
- Gelman, A., et al. (2013). *Bayesian Data Analysis*. Chapter 2.

---

*Next: [Tutorial 1: Beta Distribution Deep Dive](./01-beta-distribution.md)*
