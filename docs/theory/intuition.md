# The Restaurant Problem

## A thought experiment

You just moved to a new city. There are 10 restaurants within walking distance. You have no reviews, no recommendations, no data. You'll eat out every night for the next month.

Night 1, you pick one at random. It's incredible — maybe the best pad thai you've ever had.

Night 2. What do you do?

Go back to the pad thai place? You *know* it's good. But there are 9 other restaurants you haven't tried. One of them might be even better. Or they might all be worse. You don't know.

This is the **exploration-exploitation tradeoff**, and you solve it every day without thinking about it.

## What your gut already does

Most people converge on a strategy that looks something like this:

1. **Try a few places** in the first week (exploration)
2. **Start revisiting the good ones** once you have some data (exploitation)
3. **Occasionally try something new**, especially if a friend recommends it or you're feeling adventurous (continued exploration)
4. **Settle into a rotation** of 3-4 favorites by the end of the month (convergence)

This is a good strategy. It's not optimal, but it's remarkably close to what the best algorithms do. Your brain is doing informal Bayesian inference — updating beliefs based on experience and acting on them.

The problem is that your brain doesn't keep records. You don't track *how many times* you liked a place or *how confident* you are. You go on vibes.

Vibes work for restaurants. They don't work when the stakes are higher.

## Scaling the problem

Now imagine you're not picking restaurants. You're picking which engineering rules to show a developer before each coding session.

You have 30 candidate rules:

- "Always handle null returns from database queries"
- "Prefer composition over inheritance for service classes"
- "Write the test first when fixing a bug"

Some of these rules prevent mistakes. Some are irrelevant. Some might even be wrong. You don't know which ones help until you try them and observe what happens.

This is the same restaurant problem, but:

- You have **30 options** instead of 10
- The "meal quality" is **harder to observe** (did the rule prevent a mistake, or was the developer just lucky?)
- The **context matters** (a rule about null handling matters for database code, not for CSS)
- You need to **automate** the decision because a human can't re-evaluate 30 rules before every session

You need an algorithm. But here's the key insight: **the algorithm should work the way your gut already works** — try things, learn from experience, focus on what works, keep exploring occasionally.

That's exactly what Thompson Sampling does. But before we get there, we need to understand what we're optimizing for.

## The question that matters

When you went back to the pad thai place on night 2, you gave up the chance to discover something better. When you tried the sushi place on night 3 and it was mediocre, you gave up a guaranteed good meal.

Every choice has a cost. The question isn't how to avoid that cost — you can't. The question is: **how do you minimize it over time?**

That cost has a name. It's called [regret](regret.md).

## Key takeaway

The exploration-exploitation tradeoff isn't an abstract math problem. It's the same decision you make every time you choose between a known favorite and an unknown option. The algorithms we'll build formalize what your intuition already does — and then do it better, faster, and with receipts.

## Next

- [The Price of Learning](regret.md) — Formalizing the cost of not knowing
