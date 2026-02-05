# Keeping Score

## The problem with averages

You've been to Restaurant A five times. Four great meals, one mediocre. Your friend went to Restaurant B once and loved it.

Which is better?

If you use averages: A is 4/5 = 0.80. B is 1/1 = 1.00. B wins.

But that's absurd. You have *one data point* for B. It could be a fluke. You have five for A and a consistent track record. Your *confidence* in A is much higher than your confidence in B.

Averages throw away uncertainty. We need something that keeps it.

## Enter the Beta distribution

The Beta distribution is a way to represent "I think this option has quality *roughly here*, but I'm *this uncertain* about it."

It has two parameters: **alpha** and **beta** (unfortunately named the same as the distribution itself). Think of them as:

- **alpha** = number of successes + 1
- **beta** = number of failures + 1

For Restaurant A (4 great, 1 meh): **Beta(5, 2)**

For Restaurant B (1 great, 0 meh): **Beta(2, 1)**

For a restaurant you've never visited: **Beta(1, 1)**

### What the shape tells you

| Distribution | Shape | Meaning |
|-------------|-------|---------|
| Beta(1, 1) | Flat line | "I have no idea. Could be anything." |
| Beta(2, 1) | Slight lean right | "One success, probably decent, but who knows." |
| Beta(5, 2) | Hump near 0.80 | "Mostly good, pretty confident." |
| Beta(20, 3) | Sharp spike near 0.87 | "Very good, very confident." |
| Beta(1, 5) | Hump near 0.17 | "Mostly bad, pretty confident." |

The **width** of the distribution is your uncertainty. The **location** of the peak is your best estimate. As you collect more data, the distribution gets taller and narrower — you become more certain.

## The math (it's simpler than it looks)

### Mean: your best estimate

```
mean = alpha / (alpha + beta)
```

Restaurant A: 5 / (5 + 2) = 0.71. Restaurant B: 2 / (2 + 1) = 0.67. Beta(1, 1): 1 / 2 = 0.50.

!!! note
    The mean with Beta parameters isn't exactly the same as the raw success rate (4/5 = 0.80) because the prior adds a pseudo-observation. With enough real data, the prior washes out.

### Variance: your uncertainty

```
variance = (alpha * beta) / ((alpha + beta)^2 * (alpha + beta + 1))
```

Restaurant A: (5 * 2) / (49 * 8) = 0.026. Restaurant B: (2 * 1) / (9 * 4) = 0.056.

B has **twice the variance** of A. The math confirms what your gut already knew: you're less certain about B.

### Credible interval: the range of plausible values

The 95% credible interval tells you where the true quality probably falls:

```
CI = [mean - 1.96 * sqrt(variance), mean + 1.96 * sqrt(variance)]
```

Restaurant A: [0.40, 1.00]. Restaurant B: [0.20, 1.00].

B's interval is *huge*. It could be anywhere from mediocre to perfect. A's is narrower — you have real signal.

## Why Beta is perfect for this

The Beta distribution has a special property called **conjugacy** with binary outcomes (success/failure). This means:

1. You start with a prior: Beta(alpha, beta)
2. You observe a success → new posterior: Beta(alpha + 1, beta)
3. You observe a failure → new posterior: Beta(alpha, beta + 1)

That's it. No complex recalculation. Just add 1 to the right parameter. The posterior is *always* another Beta distribution, so you can keep updating forever without changing your framework.

This is why buildlog uses Beta distributions for its bandit: binary feedback (rule helped or didn't) maps perfectly to Beta-Bernoulli updates.

## Priors: what you believe before data

The starting distribution — the prior — encodes what you believe before any evidence. buildlog uses two priors:

| Prior | Mean | Used for | Rationale |
|-------|------|----------|-----------|
| Beta(3, 1) | 0.75 | Curated rules (from gauntlet reviews, expert seeds) | These were selected by humans. Optimistic start prevents premature pruning. |
| Beta(1, 1) | 0.50 | Extracted rules (from distillation) | Machine-extracted. Neutral prior, let the data decide. |

The optimistic prior for curated rules is a deliberate choice: it takes more evidence to demote a human-curated rule than to demote a machine-extracted one. This matches the intuition that expert judgment is a useful prior signal.

## How data overwhelms the prior

Priors matter when you have little data. They stop mattering as data accumulates.

| Observations | Prior Beta(3, 1) | Posterior (4 success, 1 failure) | Mean |
|-------------|------------------|----------------------------------|------|
| 0 | Beta(3, 1) | — | 0.75 |
| 5 | — | Beta(7, 2) | 0.78 |
| 20 | — | Beta(19, 5) | 0.79 |
| 100 | — | Beta(83, 21) | 0.80 |

After 100 observations, the posterior mean (0.80) is essentially the true success rate. The prior (0.75) has been washed out by data. This is a core property of Bayesian updating: **data always wins in the long run.**

## Confidence by observation count

| Observations | Confidence | What it means |
|-------------|------------|---------------|
| 0 | None | Prior only. Guessing. |
| 1-4 | Low | Wide distribution. Could go either way. |
| 5-19 | Medium | Starting to see a pattern. |
| 20-49 | High | Strong signal. Posterior is reliable. |
| 50+ | Very high | Converged. More data won't change much. |

## Connecting back

Now you have a way to represent "how good is this option?" that includes uncertainty. Restaurant A isn't just "0.80 good" — it's "Beta(5, 2), which peaks around 0.71 with moderate confidence."

But having good scorecards doesn't tell you what to *do*. You still need a decision rule: given these distributions, which restaurant do you go to tonight?

That's [Thompson Sampling](thompson-sampling.md).

## Key takeaway

Beta distributions encode both your best estimate *and* your uncertainty about that estimate. They update trivially with binary feedback (just add 1). They're the natural tool for tracking how good each option is when outcomes are success/failure. And they're exactly what buildlog uses to score engineering rules.

## Next

- [Making Decisions](thompson-sampling.md) — Using uncertainty to guide action
