# Tutorial 3: Thompson Sampling

**The Elegant Algorithm**

Thompson Sampling is a remarkably simple algorithm with deep theoretical properties. This tutorial explains why it works, proves it outperforms naive strategies, and walks through buildlog's `ThompsonSamplingBandit` implementation.

By the end, you'll understand why "sample, don't exploit" is the key insight.

---

## Table of Contents

1. [Why Not Just Use the Mean?](#why-not-just-use-the-mean)
2. [Why Not Epsilon-Greedy?](#why-not-epsilon-greedy)
3. [The Thompson Sampling Insight](#the-thompson-sampling-insight)
4. [Why Sampling Balances Explore-Exploit](#why-sampling-balances-explore-exploit)
5. [Regret Bounds](#regret-bounds)
6. [Code Walkthrough: select()](#code-walkthrough-select)
7. [Simulation: Watch TS Converge](#simulation-watch-ts-converge)
8. [Comparison with Other Algorithms](#comparison-with-other-algorithms)
9. [Exercises](#exercises)

---

## Why Not Just Use the Mean?

### The Greedy Approach

The obvious strategy: always pick the arm with highest estimated mean.

```python
import random
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

def greedy_select(arms):
    """Always pick arm with highest mean."""
    means = [(i, a / (a + b)) for i, (a, b) in enumerate(arms)]
    means.sort(key=lambda x: x[1], reverse=True)
    return means[0][0]

# Three arms with true rates: 0.3, 0.6, 0.5
true_rates = [0.3, 0.6, 0.5]
arms = [(1, 1), (1, 1), (1, 1)]  # Start uniform

# Simulate: first arm happens to win twice early
arms[0] = (3, 1)  # 2 wins → mean 0.75
arms[1] = (1, 2)  # 0 wins, 1 loss → mean 0.33
arms[2] = (1, 1)  # Not tried → mean 0.50

print("After unlucky start:")
for i, (a, b) in enumerate(arms):
    print(f"  Arm {i}: Beta({a}, {b}), mean={a/(a+b):.2f}, true={true_rates[i]:.1f}")

print(f"\nGreedy selects: Arm {greedy_select(arms)} (the WORST one!)")
```

Output:
```
After unlucky start:
  Arm 0: Beta(3, 1), mean=0.75, true=0.3
  Arm 1: Beta(1, 2), mean=0.33, true=0.6
  Arm 2: Beta(1, 1), mean=0.50, true=0.5

Greedy selects: Arm 0 (the WORST one!)
```

### The Problem: Premature Convergence

Greedy locks onto early winners and never explores alternatives:

```python
def simulate_greedy(true_rates, n_rounds=1000):
    """Simulate greedy algorithm."""
    k = len(true_rates)
    arms = [(1, 1) for _ in range(k)]
    selections = []

    for _ in range(n_rounds):
        # Select greedily
        arm = greedy_select(arms)
        selections.append(arm)

        # Observe outcome
        reward = 1 if random.random() < true_rates[arm] else 0
        a, b = arms[arm]
        arms[arm] = (a + reward, b + (1 - reward))

    return selections, arms

random.seed(42)
true_rates = [0.3, 0.6, 0.5]
selections, final_arms = simulate_greedy(true_rates)

print("Pull distribution over 1000 rounds:")
for i in range(3):
    count = selections.count(i)
    print(f"  Arm {i} (true={true_rates[i]}): {count} pulls ({count/10:.1f}%)")
```

Typical output:
```
Pull distribution over 1000 rounds:
  Arm 0 (true=0.3): 987 pulls (98.7%)
  Arm 1 (true=0.6): 8 pulls (0.8%)
  Arm 2 (true=0.5): 5 pulls (0.5%)
```

Greedy got stuck on Arm 0 (the worst!) because it happened to win early.

---

## Why Not Epsilon-Greedy?

### The Idea

Epsilon-greedy explores with probability ε, exploits otherwise:

```python
def epsilon_greedy_select(arms, epsilon=0.1):
    """Explore with probability epsilon, else exploit."""
    if random.random() < epsilon:
        return random.randint(0, len(arms) - 1)  # Random exploration
    return greedy_select(arms)  # Exploitation
```

### Problems

**1. Wastes exploration on known-bad arms:**

```python
# After 1000 observations, you KNOW arm 0 is bad
# But epsilon-greedy still explores it 1/3 of the time
arms = [(10, 90), (70, 30), (50, 50)]  # Means: 0.10, 0.70, 0.50

# With ε=0.1, you pull the 10% arm about 3.3% of the time
# That's pure waste!
```

**2. Hyperparameter sensitivity:**

```python
def compare_epsilons(true_rates, epsilons, n_rounds=1000):
    """Compare different epsilon values."""
    results = {}

    for eps in epsilons:
        random.seed(42)
        arms = [(1, 1) for _ in range(len(true_rates))]
        total_reward = 0

        for _ in range(n_rounds):
            arm = epsilon_greedy_select(arms, eps)
            reward = 1 if random.random() < true_rates[arm] else 0
            total_reward += reward
            a, b = arms[arm]
            arms[arm] = (a + reward, b + (1 - reward))

        results[eps] = total_reward

    return results

true_rates = [0.3, 0.6, 0.5]
epsilons = [0.01, 0.05, 0.1, 0.2, 0.3, 0.5]
results = compare_epsilons(true_rates, epsilons)

print("Rewards by epsilon:")
for eps, reward in results.items():
    print(f"  ε={eps:.2f}: {reward} (optimal: {int(0.6 * 1000)})")
```

**3. Explores uniformly, not intelligently:**

```python
# These two arms have very different uncertainty:
arm_a = (3, 2)   # 5 observations, mean 0.60
arm_b = (60, 40) # 100 observations, mean 0.60

# Epsilon-greedy explores both with equal probability
# But we should explore arm_a more (we're less certain about it!)
```

---

## The Thompson Sampling Insight

### The Algorithm

Thompson Sampling is elegantly simple:

```
For each arm:
    Sample a value from its posterior distribution
Select the arm with the highest sample
```

That's it. No hyperparameters. No explicit explore/exploit tradeoff.

```python
def thompson_sample(alpha, beta):
    """Draw one sample from Beta(alpha, beta)."""
    return random.betavariate(alpha, beta)

def thompson_select(arms):
    """Select arm via Thompson Sampling."""
    samples = [(i, thompson_sample(a, b)) for i, (a, b) in enumerate(arms)]
    samples.sort(key=lambda x: x[1], reverse=True)
    return samples[0][0]
```

### Why It Works: An Intuitive Explanation

Consider two arms:
- **Arm A**: Beta(3, 2) — mean 0.60, few observations, high variance
- **Arm B**: Beta(60, 40) — mean 0.60, many observations, low variance

Both have the same mean. But when we sample:

```python
def sampling_demo():
    """Show how sampling naturally explores uncertain arms."""
    arm_a = (3, 2)   # High variance
    arm_b = (60, 40)  # Low variance

    n_samples = 10000
    a_wins = 0

    for _ in range(n_samples):
        sample_a = random.betavariate(*arm_a)
        sample_b = random.betavariate(*arm_b)
        if sample_a > sample_b:
            a_wins += 1

    print(f"Both arms have mean = 0.60")
    print(f"Arm A (uncertain) wins {a_wins/n_samples:.1%} of selections")
    print(f"Arm B (confident) wins {(n_samples-a_wins)/n_samples:.1%} of selections")

    # Visualize
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    x = np.linspace(0, 1, 1000)

    for ax, (a, b), name in [(axes[0], arm_a, 'Arm A: Beta(3,2)'),
                               (axes[1], arm_b, 'Arm B: Beta(60,40)')]:
        pdf = stats.beta.pdf(x, a, b)
        ax.plot(x, pdf, 'steelblue', linewidth=2)
        ax.fill_between(x, pdf, alpha=0.3)
        ax.axvline(a/(a+b), color='red', linestyle='--', label=f'Mean: {a/(a+b):.2f}')
        ax.set_title(name)
        ax.set_xlim(0, 1)
        ax.legend()

    plt.tight_layout()
    plt.savefig('uncertainty_comparison.png', dpi=150)
    plt.show()

random.seed(42)
sampling_demo()
```

Output:
```
Both arms have mean = 0.60
Arm A (uncertain) wins 50.2% of selections
Arm B (confident) wins 49.8% of selections
```

With same means, selection is ~50/50. But Arm A's samples vary more wildly (sometimes 0.2, sometimes 0.9), while Arm B's cluster tightly around 0.6.

### The Magic: Uncertainty Drives Exploration

```python
def show_exploration_mechanism():
    """Demonstrate how uncertainty creates exploration."""
    # Arm A: looks good (mean 0.7) but uncertain
    arm_a = (4, 2)  # mean 0.67, 6 pseudo-observations

    # Arm B: looks slightly worse (mean 0.6) but very certain
    arm_b = (60, 40)  # mean 0.60, 100 pseudo-observations

    samples_a = [random.betavariate(*arm_a) for _ in range(1000)]
    samples_b = [random.betavariate(*arm_b) for _ in range(1000)]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(samples_a, bins=50, alpha=0.5, label=f'Arm A: Beta{arm_a}, mean={arm_a[0]/sum(arm_a):.2f}', density=True)
    ax.hist(samples_b, bins=50, alpha=0.5, label=f'Arm B: Beta{arm_b}, mean={arm_b[0]/sum(arm_b):.2f}', density=True)
    ax.axvline(arm_a[0]/sum(arm_a), color='blue', linestyle='--', alpha=0.7)
    ax.axvline(arm_b[0]/sum(arm_b), color='orange', linestyle='--', alpha=0.7)
    ax.set_xlabel('Sampled Value')
    ax.set_ylabel('Density')
    ax.set_title('Thompson Sampling: Uncertain Arm Gets Explored')
    ax.legend()
    plt.savefig('exploration_mechanism.png', dpi=150)
    plt.show()

    # Count how often each wins
    a_wins = sum(1 for sa, sb in zip(samples_a, samples_b) if sa > sb)
    print(f"Arm A (uncertain, higher mean) wins: {a_wins/10:.1f}%")
    print(f"Arm B (certain, lower mean) wins: {(1000-a_wins)/10:.1f}%")

show_exploration_mechanism()
```

The uncertain arm sometimes samples very high (exploration!) even though its mean is only slightly higher. As we gather more data about it, variance decreases, and selection becomes more deterministic.

---

## Why Sampling Balances Explore-Exploit

### Probability Matching

Thompson Sampling selects each arm with probability equal to the probability that it's optimal:

```
P(select arm i) = P(arm i is best | data)
```

This is called **probability matching** and it's provably optimal in certain settings.

```python
def verify_probability_matching():
    """Show that TS selection probability matches posterior probability of being best."""
    # True rates (unknown to algorithm)
    true_rates = [0.4, 0.6, 0.5]

    # After some observations
    arms = [
        (5, 8),   # Observed: 4/12, true: 0.4
        (8, 5),   # Observed: 7/12, true: 0.6
        (6, 6),   # Observed: 5/10, true: 0.5
    ]

    # Estimate P(arm i is best) via Monte Carlo
    n_samples = 50000
    best_counts = [0, 0, 0]

    for _ in range(n_samples):
        samples = [random.betavariate(a, b) for a, b in arms]
        best = samples.index(max(samples))
        best_counts[best] += 1

    print("Probability each arm is best (estimated via Monte Carlo):")
    for i, count in enumerate(best_counts):
        print(f"  Arm {i}: {count/n_samples:.1%}")

    # Now run Thompson Sampling many times and see if selection matches
    ts_selections = [0, 0, 0]
    for _ in range(n_samples):
        samples = [random.betavariate(a, b) for a, b in arms]
        selected = samples.index(max(samples))
        ts_selections[selected] += 1

    print("\nThompson Sampling selection frequency:")
    for i, count in enumerate(ts_selections):
        print(f"  Arm {i}: {count/n_samples:.1%}")

    print("\n→ They match! TS selects proportionally to P(best).")

verify_probability_matching()
```

### Automatic Annealing

Unlike epsilon-greedy where you must tune ε, Thompson Sampling automatically:

1. **Explores heavily early** (high variance → random samples)
2. **Exploits more over time** (low variance → samples cluster near mean)
3. **Never completely stops exploring** (always some variance)

```python
def show_annealing():
    """Show how exploration naturally decreases over time."""
    true_rate = 0.6
    n_rounds = 500

    # Track variance over time
    variances = []
    alpha, beta = 1, 1

    for _ in range(n_rounds):
        var = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
        variances.append(var)

        reward = 1 if random.random() < true_rate else 0
        alpha += reward
        beta += (1 - reward)

    plt.figure(figsize=(10, 5))
    plt.plot(variances, 'steelblue', linewidth=2)
    plt.xlabel('Round')
    plt.ylabel('Posterior Variance')
    plt.title('Automatic Annealing: Variance Decreases with Data')
    plt.yscale('log')
    plt.savefig('annealing.png', dpi=150)
    plt.show()

show_annealing()
```

---

## Regret Bounds

### What Is Regret?

Regret measures how much reward you lost compared to always pulling the best arm:

```
Regret(T) = T × μ* - Σ rewards
```

Where μ* is the best arm's true rate.

### Thompson Sampling's Guarantee

For K arms over T rounds, Thompson Sampling achieves:

```
E[Regret(T)] = O(√(KT log K))
```

This is **sublinear**—regret grows slower than linearly with time.

```python
def visualize_regret_bounds():
    """Visualize different regret growth rates."""
    T = np.arange(1, 10001)
    K = 5

    linear = T * 0.1  # Linear: regret grows with T
    sqrt = 10 * np.sqrt(K * T * np.log(K))  # TS bound
    log = 20 * K * np.log(T)  # UCB-style bound

    plt.figure(figsize=(10, 6))
    plt.plot(T, linear, 'r-', label='Linear (bad algorithm)', linewidth=2)
    plt.plot(T, sqrt, 'g-', label='O(√(KT log K)) - Thompson Sampling', linewidth=2)
    plt.plot(T, log, 'b-', label='O(K log T) - Optimal (UCB)', linewidth=2)
    plt.xlabel('Time (T)')
    plt.ylabel('Cumulative Regret')
    plt.title('Regret Growth Rates')
    plt.legend()
    plt.savefig('regret_bounds.png', dpi=150)
    plt.show()

visualize_regret_bounds()
```

### Empirical Regret

Let's measure actual regret:

```python
def measure_regret(algorithm, true_rates, n_rounds=1000, n_simulations=100):
    """Measure average regret for an algorithm."""
    best_rate = max(true_rates)
    all_regrets = []

    for _ in range(n_simulations):
        arms = [(1, 1) for _ in range(len(true_rates))]
        cumulative_regret = 0
        regret_history = []

        for _ in range(n_rounds):
            arm = algorithm(arms)
            reward = 1 if random.random() < true_rates[arm] else 0

            # Update arm
            a, b = arms[arm]
            arms[arm] = (a + reward, b + (1 - reward))

            # Track regret
            instant_regret = best_rate - true_rates[arm]
            cumulative_regret += instant_regret
            regret_history.append(cumulative_regret)

        all_regrets.append(regret_history)

    return np.mean(all_regrets, axis=0)

true_rates = [0.3, 0.6, 0.5, 0.4]

algorithms = {
    'Thompson Sampling': thompson_select,
    'Greedy': greedy_select,
    'ε-Greedy (0.1)': lambda arms: epsilon_greedy_select(arms, 0.1),
}

plt.figure(figsize=(10, 6))
for name, alg in algorithms.items():
    random.seed(42)
    regrets = measure_regret(alg, true_rates)
    plt.plot(regrets, label=name, linewidth=2)

plt.xlabel('Round')
plt.ylabel('Cumulative Regret')
plt.title('Regret Comparison: Thompson Sampling vs Alternatives')
plt.legend()
plt.savefig('regret_comparison.png', dpi=150)
plt.show()
```

---

## Code Walkthrough: select()

From `src/buildlog/core/bandit.py`:

```python
def select(
    self,
    candidates: list[str],
    context: str | None = None,
    k: int = 3,
    seed_rule_ids: set[str] | None = None,
) -> list[str]:
    """Select top-k rules using Thompson Sampling.

    This is where the magic happens:

    1. For each candidate rule, get or create its Beta distribution
    2. Sample from each distribution (not the mean!)
    3. Return the k rules with highest samples

    The sampling step is crucial: it means rules we're uncertain about
    (high variance) will occasionally beat rules with higher means,
    ensuring we explore enough to learn their true values.
    """
    ctx = context or self.default_context
    seed_ids = seed_rule_ids or set()

    # Sample from each candidate's distribution
    samples: list[tuple[str, float]] = []

    for rule_id in candidates:
        params = self.state.get_params(ctx, rule_id)

        if params is None:
            # Initialize new arm
            is_seed = rule_id in seed_ids
            params = self._create_prior(is_seed)
            self.state.set_params(ctx, rule_id, params, is_seed)

        # THE KEY STEP: sample, don't use mean
        sample = params.sample()
        samples.append((rule_id, sample))

    # Sort by sampled value (descending) and take top k
    samples.sort(key=lambda x: x[1], reverse=True)
    selected = [rule_id for rule_id, _ in samples[:k]]

    # Persist any new arms we created
    self.state.save(self.state_path)

    return selected
```

### Line by Line

**Get or create Beta parameters:**
```python
params = self.state.get_params(ctx, rule_id)

if params is None:
    is_seed = rule_id in seed_ids
    params = self._create_prior(is_seed)
    self.state.set_params(ctx, rule_id, params, is_seed)
```

New rules get initialized. Seed rules get boosted priors (Beta(3, 1) instead of Beta(1, 1)).

**THE KEY STEP:**
```python
sample = params.sample()  # NOT params.mean()!
```

This single line is Thompson Sampling. We draw from the posterior, not use the point estimate.

**Select top-k:**
```python
samples.sort(key=lambda x: x[1], reverse=True)
selected = [rule_id for rule_id, _ in samples[:k]]
```

Rules with highest samples win. Uncertain rules occasionally sample high enough to be selected.

### Seed-Boosted Priors

```python
def _create_prior(self, is_seed: bool) -> BetaParams:
    if is_seed:
        # Beta(1 + 2, 1) = Beta(3, 1) → mean = 0.75
        return BetaParams(alpha=1.0 + self.seed_boost, beta=1.0)
    else:
        # Beta(1, 1) → mean = 0.50, uniform uncertainty
        return BetaParams(alpha=1.0, beta=1.0)
```

Seed rules (from gauntlet personas) start with "2 extra successes"—we believe they're likely good based on expert curation.

---

## Simulation: Watch TS Converge

### Full Simulation

```python
def full_thompson_simulation():
    """Complete simulation showing TS learning over time."""
    true_rates = [0.3, 0.7, 0.5, 0.4]  # Arm 1 is best
    n_rounds = 500
    k = len(true_rates)

    arms = [(1, 1) for _ in range(k)]
    selections = []
    means_over_time = [[] for _ in range(k)]

    for t in range(n_rounds):
        # Thompson Sampling selection
        samples = [(i, random.betavariate(a, b)) for i, (a, b) in enumerate(arms)]
        samples.sort(key=lambda x: x[1], reverse=True)
        arm = samples[0][0]
        selections.append(arm)

        # Observe reward
        reward = 1 if random.random() < true_rates[arm] else 0
        a, b = arms[arm]
        arms[arm] = (a + reward, b + (1 - reward))

        # Record means
        for i, (a, b) in enumerate(arms):
            means_over_time[i].append(a / (a + b))

    # Visualize
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # 1. Selection frequency over time (windowed)
    ax = axes[0, 0]
    window = 50
    for i in range(k):
        freq = [selections[max(0,t-window):t].count(i) / min(t, window)
                for t in range(1, n_rounds + 1)]
        ax.plot(freq, label=f'Arm {i} (true={true_rates[i]})', linewidth=1.5)
    ax.set_xlabel('Round')
    ax.set_ylabel(f'Selection Frequency (last {window})')
    ax.set_title('Selection Converges to Best Arm')
    ax.legend()

    # 2. Mean estimates over time
    ax = axes[0, 1]
    for i in range(k):
        ax.plot(means_over_time[i], label=f'Arm {i}', linewidth=1.5)
        ax.axhline(true_rates[i], linestyle=':', alpha=0.5)
    ax.set_xlabel('Round')
    ax.set_ylabel('Posterior Mean')
    ax.set_title('Estimates Converge to True Rates')
    ax.legend()

    # 3. Final distributions
    ax = axes[1, 0]
    x = np.linspace(0, 1, 1000)
    for i, (a, b) in enumerate(arms):
        pdf = stats.beta.pdf(x, a, b)
        ax.plot(x, pdf, label=f'Arm {i}: Beta({a:.0f},{b:.0f})', linewidth=2)
        ax.axvline(true_rates[i], linestyle=':', color=f'C{i}', alpha=0.5)
    ax.set_xlabel('Rate')
    ax.set_ylabel('Density')
    ax.set_title('Final Posterior Distributions')
    ax.legend()

    # 4. Total pulls per arm
    ax = axes[1, 1]
    pull_counts = [selections.count(i) for i in range(k)]
    bars = ax.bar(range(k), pull_counts, color=[f'C{i}' for i in range(k)])
    ax.set_xlabel('Arm')
    ax.set_ylabel('Total Pulls')
    ax.set_title('Pull Distribution')
    for i, (count, rate) in enumerate(zip(pull_counts, true_rates)):
        ax.text(i, count + 5, f'{count}\n(true={rate})', ha='center', fontsize=9)

    plt.tight_layout()
    plt.savefig('ts_simulation.png', dpi=150)
    plt.show()

    print(f"\nFinal pull counts: {[selections.count(i) for i in range(k)]}")
    print(f"Best arm (1) pulled {selections.count(1)/n_rounds:.1%} of the time")

random.seed(42)
full_thompson_simulation()
```

---

## Comparison with Other Algorithms

### UCB (Upper Confidence Bound)

UCB uses confidence bounds instead of sampling:

```python
def ucb_select(arms, t, c=2.0):
    """Upper Confidence Bound selection."""
    ucb_values = []
    for i, (a, b) in enumerate(arms):
        n = a + b - 2  # Number of observations (subtract prior)
        if n == 0:
            ucb_values.append((i, float('inf')))  # Explore untried arms
        else:
            mean = a / (a + b)
            bonus = c * np.sqrt(np.log(t + 1) / n)
            ucb_values.append((i, mean + bonus))

    ucb_values.sort(key=lambda x: x[1], reverse=True)
    return ucb_values[0][0]
```

**Thompson Sampling vs UCB:**

| Aspect | Thompson Sampling | UCB |
|--------|-------------------|-----|
| Exploration | Stochastic (sampling) | Deterministic (confidence bound) |
| Hyperparameters | None | Exploration constant c |
| Theoretical guarantees | O(√(KT log K)) | O(√(KT log T)) |
| Empirical performance | Often better | Slightly more conservative |
| Implementation | Simple | Simple |
| Batching | Natural (independent samples) | Awkward (same UCB for batch) |

### Head-to-Head Comparison

```python
def compare_algorithms():
    """Compare TS, UCB, ε-greedy, and Greedy."""
    true_rates = [0.3, 0.55, 0.5, 0.45]
    n_rounds = 1000
    n_sims = 50

    algorithms = {
        'Thompson Sampling': lambda arms, t: thompson_select(arms),
        'UCB (c=2)': lambda arms, t: ucb_select(arms, t, c=2.0),
        'ε-Greedy (0.1)': lambda arms, t: epsilon_greedy_select(arms, 0.1),
        'Greedy': lambda arms, t: greedy_select(arms),
    }

    results = {name: [] for name in algorithms}
    best_rate = max(true_rates)

    for name, alg in algorithms.items():
        for _ in range(n_sims):
            arms = [(1, 1) for _ in range(len(true_rates))]
            total_reward = 0

            for t in range(n_rounds):
                arm = alg(arms, t)
                reward = 1 if random.random() < true_rates[arm] else 0
                total_reward += reward
                a, b = arms[arm]
                arms[arm] = (a + reward, b + (1 - reward))

            results[name].append(total_reward)

    # Plot
    plt.figure(figsize=(10, 6))
    positions = range(len(algorithms))
    means = [np.mean(results[name]) for name in algorithms]
    stds = [np.std(results[name]) for name in algorithms]

    bars = plt.bar(positions, means, yerr=stds, capsize=5,
                   color=['steelblue', 'orange', 'green', 'red'])
    plt.xticks(positions, algorithms.keys(), rotation=15)
    plt.ylabel('Total Reward (1000 rounds)')
    plt.axhline(best_rate * n_rounds, color='black', linestyle='--',
                label=f'Optimal: {best_rate * n_rounds:.0f}')
    plt.title('Algorithm Comparison')
    plt.legend()
    plt.tight_layout()
    plt.savefig('algorithm_comparison.png', dpi=150)
    plt.show()

    for name in algorithms:
        print(f"{name}: {np.mean(results[name]):.1f} ± {np.std(results[name]):.1f}")

random.seed(42)
compare_algorithms()
```

---

## Exercises

### Conceptual Exercises

**Exercise 3.1: Sampling vs Mean**

Two arms:
- A: Beta(10, 10), mean = 0.50
- B: Beta(2, 1), mean = 0.67

Which arm is more likely to be selected by Thompson Sampling? Why?

<details>
<summary>Solution</summary>

**Arm B** is more likely to be selected, but not by much.

- Arm A has mean 0.50 with low variance (confident)
- Arm B has mean 0.67 with high variance (uncertain)

When we sample:
- Arm A samples cluster around 0.50
- Arm B samples spread widely, often below 0.50, sometimes above 0.80

Monte Carlo shows B wins ~60-65% of the time. Its higher mean plus occasional very high samples give it an edge.

```python
a_wins = sum(1 for _ in range(10000)
             if random.betavariate(10, 10) < random.betavariate(2, 1))
print(f"B wins: {a_wins/100:.1f}%")  # ~62%
```

</details>

---

**Exercise 3.2: Cold Start**

You have 10 rules, all new (Beta(1,1)). After selecting k=3 rules in the first session, what happens to their distributions if all get reward=0?

<details>
<summary>Solution</summary>

The 3 selected rules update from Beta(1, 1) to Beta(1, 2):
- Mean drops from 0.50 to 0.33
- The 7 unselected rules remain at Beta(1, 1), mean = 0.50

In the next selection:
- Unselected rules now have higher means
- Thompson Sampling will likely select different rules
- This is natural exploration: try others when first picks fail

</details>

---

**Exercise 3.3: Seed Boost**

A seed rule starts with Beta(3, 1) (mean 0.75). A learned rule starts with Beta(1, 1) (mean 0.50). After how many failures does the seed rule's mean drop below the learned rule's initial mean?

<details>
<summary>Solution</summary>

Seed: Beta(3, 1) → mean = 0.75

After k failures: Beta(3, 1+k) → mean = 3/(4+k)

We want: 3/(4+k) < 0.50

Solving: 3 < 0.5(4+k) = 2 + 0.5k
         1 < 0.5k
         k > 2

After **3 failures**, seed rule has Beta(3, 4), mean = 0.43 < 0.50.

The seed boost gives the rule 2 "lives" before being demoted below a fresh rule.

</details>

---

### Coding Exercises

**Exercise 3.4: Implement Top-k Thompson Sampling**

Extend the basic Thompson Sampling to select k items:

```python
def thompson_select_k(arms, k):
    """Select top-k arms via Thompson Sampling."""
    # YOUR CODE HERE
    pass

# Test
arms = [(5, 3), (3, 5), (10, 2), (2, 10)]
selected = thompson_select_k(arms, k=2)
print(f"Selected arms: {selected}")
```

<details>
<summary>Solution</summary>

```python
def thompson_select_k(arms, k):
    samples = [(i, random.betavariate(a, b)) for i, (a, b) in enumerate(arms)]
    samples.sort(key=lambda x: x[1], reverse=True)
    return [i for i, _ in samples[:k]]
```

</details>

---

**Exercise 3.5: Visualize Exploration Decay**

Create a visualization showing how Thompson Sampling's exploration naturally decreases as confidence increases.

```python
def visualize_exploration_decay(true_rates, n_rounds=500):
    """
    Track and visualize how often TS explores (selects non-best arm)
    over time as posteriors tighten.
    """
    # YOUR CODE HERE
    pass
```

<details>
<summary>Solution</summary>

```python
def visualize_exploration_decay(true_rates, n_rounds=500):
    k = len(true_rates)
    best_arm = true_rates.index(max(true_rates))
    arms = [(1, 1) for _ in range(k)]

    exploration_rate = []
    window = 20

    selections = []
    for t in range(n_rounds):
        # Thompson Sampling
        samples = [(i, random.betavariate(a, b)) for i, (a, b) in enumerate(arms)]
        samples.sort(key=lambda x: x[1], reverse=True)
        arm = samples[0][0]
        selections.append(arm)

        # Update
        reward = 1 if random.random() < true_rates[arm] else 0
        a, b = arms[arm]
        arms[arm] = (a + reward, b + (1 - reward))

        # Track exploration rate (selected != best)
        recent = selections[max(0, t-window+1):t+1]
        explore_rate = sum(1 for s in recent if s != best_arm) / len(recent)
        exploration_rate.append(explore_rate)

    plt.figure(figsize=(10, 5))
    plt.plot(exploration_rate, 'steelblue', linewidth=2)
    plt.xlabel('Round')
    plt.ylabel(f'Exploration Rate (last {window} rounds)')
    plt.title('Thompson Sampling: Exploration Naturally Decays')
    plt.axhline(0, color='gray', linestyle='--', alpha=0.5)
    plt.savefig('exploration_decay.png', dpi=150)
    plt.show()

random.seed(42)
visualize_exploration_decay([0.3, 0.6, 0.5])
```

</details>

---

**Exercise 3.6: Batched Thompson Sampling**

In buildlog, we select k rules at session start, then all get the same feedback at session end. Implement and analyze batched feedback:

```python
def batched_thompson(true_rates, k, n_sessions, mistakes_per_session=5):
    """
    Simulate batched Thompson Sampling:
    - Select k rules per session
    - All selected rules get same feedback
    - Repeat for n_sessions
    """
    # YOUR CODE HERE
    pass
```

<details>
<summary>Solution</summary>

```python
def batched_thompson(true_rates, k, n_sessions, session_length=10):
    n_rules = len(true_rates)
    arms = [(1, 1) for _ in range(n_rules)]

    for session in range(n_sessions):
        # Select k rules
        samples = [(i, random.betavariate(a, b)) for i, (a, b) in enumerate(arms)]
        samples.sort(key=lambda x: x[1], reverse=True)
        selected = [i for i, _ in samples[:k]]

        # Simulate session: rules prevent mistakes based on true rates
        # Average effectiveness of selected rules
        combined_rate = np.mean([true_rates[i] for i in selected])

        # Each "event" in session: did rules help?
        for _ in range(session_length):
            success = random.random() < combined_rate
            reward = 1.0 if success else 0.0

            # All selected rules get same feedback
            for i in selected:
                a, b = arms[i]
                arms[i] = (a + reward, b + (1 - reward))

    return arms

# Compare: which rules learned most?
true_rates = [0.2, 0.7, 0.5, 0.3, 0.6]
final_arms = batched_thompson(true_rates, k=2, n_sessions=50)

print("Final estimates:")
for i, (a, b) in enumerate(final_arms):
    print(f"  Rule {i}: true={true_rates[i]:.1f}, estimated={a/(a+b):.2f}, obs={a+b-2:.0f}")
```

</details>

---

### Challenge Exercises

**Exercise 3.7: Contextual Preview**

Extend Thompson Sampling to handle multiple contexts (preview of Tutorial 4):

```python
class ContextualThompsonSampling:
    """Thompson Sampling with context-dependent distributions."""

    def __init__(self):
        # arms[context][rule_id] = (alpha, beta)
        self.arms = {}

    def select(self, candidates, context, k=3):
        # YOUR CODE HERE
        pass

    def update(self, rule_id, reward, context):
        # YOUR CODE HERE
        pass
```

<details>
<summary>Solution</summary>

```python
class ContextualThompsonSampling:
    def __init__(self):
        self.arms = {}

    def select(self, candidates, context, k=3):
        if context not in self.arms:
            self.arms[context] = {}

        samples = []
        for rule_id in candidates:
            if rule_id not in self.arms[context]:
                self.arms[context][rule_id] = (1, 1)
            a, b = self.arms[context][rule_id]
            samples.append((rule_id, random.betavariate(a, b)))

        samples.sort(key=lambda x: x[1], reverse=True)
        return [rule_id for rule_id, _ in samples[:k]]

    def update(self, rule_id, reward, context):
        if context not in self.arms:
            self.arms[context] = {}
        if rule_id not in self.arms[context]:
            self.arms[context][rule_id] = (1, 1)

        a, b = self.arms[context][rule_id]
        self.arms[context][rule_id] = (a + reward, b + (1 - reward))
```

</details>

---

**Exercise 3.8: Regret Analysis**

Implement a function that computes and plots cumulative regret with confidence bands across multiple simulations:

```python
def regret_analysis(algorithm, true_rates, n_rounds=1000, n_sims=100):
    """
    Compute regret with confidence bands.

    Returns:
        mean_regret: Array of mean cumulative regret at each round
        ci_low, ci_high: 95% confidence interval bounds
    """
    # YOUR CODE HERE
    pass
```

<details>
<summary>Solution</summary>

```python
def regret_analysis(algorithm, true_rates, n_rounds=1000, n_sims=100):
    best_rate = max(true_rates)
    all_regrets = np.zeros((n_sims, n_rounds))

    for sim in range(n_sims):
        arms = [(1, 1) for _ in range(len(true_rates))]
        cumulative = 0

        for t in range(n_rounds):
            arm = algorithm(arms, t)
            reward = 1 if random.random() < true_rates[arm] else 0
            a, b = arms[arm]
            arms[arm] = (a + reward, b + (1 - reward))

            cumulative += best_rate - true_rates[arm]
            all_regrets[sim, t] = cumulative

    mean_regret = np.mean(all_regrets, axis=0)
    std_regret = np.std(all_regrets, axis=0)
    ci_low = mean_regret - 1.96 * std_regret / np.sqrt(n_sims)
    ci_high = mean_regret + 1.96 * std_regret / np.sqrt(n_sims)

    plt.figure(figsize=(10, 6))
    plt.plot(mean_regret, 'steelblue', linewidth=2, label='Mean Regret')
    plt.fill_between(range(n_rounds), ci_low, ci_high, alpha=0.3, label='95% CI')
    plt.xlabel('Round')
    plt.ylabel('Cumulative Regret')
    plt.title('Regret Analysis with Confidence Bands')
    plt.legend()
    plt.savefig('regret_analysis.png', dpi=150)
    plt.show()

    return mean_regret, ci_low, ci_high

random.seed(42)
regret_analysis(thompson_select, [0.3, 0.6, 0.5])
```

</details>

---

**Exercise 3.9: Implement UCB and Compare**

Implement UCB1 and create a head-to-head comparison with Thompson Sampling:

```python
def ucb1_select(arms, t, c=2.0):
    """UCB1 algorithm."""
    # YOUR CODE HERE
    pass

def head_to_head(n_rounds=2000, n_sims=50):
    """Run TS vs UCB head-to-head and visualize."""
    # YOUR CODE HERE
    pass
```

<details>
<summary>Solution</summary>

```python
import math

def ucb1_select(arms, t, c=2.0):
    ucb_values = []
    total_pulls = sum(a + b - 2 for a, b in arms)

    for i, (a, b) in enumerate(arms):
        n = a + b - 2
        if n == 0:
            return i  # Always try untried arms first

        mean = a / (a + b)
        bonus = c * math.sqrt(math.log(total_pulls + 1) / n)
        ucb_values.append((i, mean + bonus))

    return max(ucb_values, key=lambda x: x[1])[0]

def head_to_head(true_rates, n_rounds=2000, n_sims=50):
    ts_rewards = []
    ucb_rewards = []

    for _ in range(n_sims):
        # Thompson Sampling
        arms = [(1, 1) for _ in true_rates]
        ts_total = 0
        for t in range(n_rounds):
            arm = thompson_select(arms)
            reward = 1 if random.random() < true_rates[arm] else 0
            ts_total += reward
            a, b = arms[arm]
            arms[arm] = (a + reward, b + (1 - reward))
        ts_rewards.append(ts_total)

        # UCB
        arms = [(1, 1) for _ in true_rates]
        ucb_total = 0
        for t in range(n_rounds):
            arm = ucb1_select(arms, t)
            reward = 1 if random.random() < true_rates[arm] else 0
            ucb_total += reward
            a, b = arms[arm]
            arms[arm] = (a + reward, b + (1 - reward))
        ucb_rewards.append(ucb_total)

    print(f"Thompson Sampling: {np.mean(ts_rewards):.1f} ± {np.std(ts_rewards):.1f}")
    print(f"UCB1:              {np.mean(ucb_rewards):.1f} ± {np.std(ucb_rewards):.1f}")
    print(f"Optimal:           {max(true_rates) * n_rounds:.0f}")

random.seed(42)
head_to_head([0.3, 0.6, 0.5, 0.4])
```

</details>

---

## Summary

You now understand:

1. **Why greedy fails:** Locks onto early winners, never explores
2. **Why ε-greedy is suboptimal:** Wastes exploration, requires tuning
3. **The Thompson Sampling insight:** Sample, don't exploit
4. **Why it works:** Uncertainty-aware exploration via posterior sampling
5. **Regret bounds:** O(√(KT log K)) sublinear regret
6. **The implementation:** `params.sample()` is the key line

In **Tutorial 4**, we'll extend this to contextual bandits—different distributions for different error classes.

---

*Previous: [Tutorial 2: Bayesian Updates](./02-bayesian-updates.md)*

*Next: [Tutorial 4: Contextual Extension](./04-contextual-bandits.md)*
