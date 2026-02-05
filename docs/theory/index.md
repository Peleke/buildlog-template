# Theory

## From intuition to implementation

You already solve bandit problems every day. You just don't call them that.

This series builds from everyday decision-making to the exact algorithm buildlog uses to select rules. No prerequisites beyond curiosity. By the end, the math won't feel like math — it'll feel like common sense you finally have notation for.

## The arc

| Page | What you'll learn | The intuition |
|------|-------------------|---------------|
| [The Restaurant Problem](intuition.md) | Exploration vs. exploitation | Trying new restaurants vs. going to your favorite |
| [The Price of Learning](regret.md) | Regret and why it matters | Every bad meal is a missed good one |
| [Keeping Score](beta-distributions.md) | Beta distributions | How to represent "I think this is good but I'm not sure" |
| [Making Decisions](thompson-sampling.md) | Thompson Sampling | Let uncertainty guide exploration |
| [Context Changes Everything](contextual-bandits.md) | Contextual bandits | You wouldn't pick the same restaurant for a date and a quick lunch |

## Where this connects

buildlog uses a Thompson Sampling contextual bandit to decide which engineering rules to surface in your editor. The "restaurants" are rules. The "meals" are coding sessions. The "reviews" are whether you made the same mistake again.

Everything in this series maps directly to `src/buildlog/core/bandit.py`. The theory isn't academic — it's the code running in your terminal.

## Who this is for

- **Engineers** who want to understand *why* Thompson Sampling, not just *that* it works
- **The curious** who want intuition before formalism
- **Skeptics** who want to verify the math themselves

No probability background required. If you can follow a restaurant analogy, you can follow the math.
