# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "numpy",
#     "matplotlib",
# ]
# ///

import marimo

__generated_with = "0.19.5"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
    # On Learning What Works

    **Time**: ~30-40 minutes | **Prerequisites**: Basic Python, curiosity about how learning happens

    ---

    There is a beautiful tension at the heart of learning itself.

    To improve, you must try new things—venture into unknown territory, risk failure, gather
    information about what you don't yet understand. But to *perform well*, you must exploit what
    you already know—stick with what works, avoid costly mistakes, capitalize on hard-won knowledge.

    Every teacher faces this tension. Every scientist faces it. Every organism that has ever
    adapted to an environment faces it. The question—how to balance exploration against
    exploitation—sounds philosophical, and it is. But it also admits a precise mathematical
    treatment, one that has been discovered and rediscovered independently by statisticians,
    economists, psychologists, and machine learning researchers over the past century.

    I find this convergence remarkable. When thinkers from different traditions, asking different
    questions, arrive at the same mathematical structure, it suggests we've touched something real—
    some genuine feature of how learning must work in an uncertain world.

    The algorithm we'll build today, **Thompson Sampling**, is perhaps the most elegant solution
    to this problem ever devised. It was published in 1933 by William R. Thompson, a statistician
    working on clinical trials, and then largely forgotten for decades. Rediscovered in the 2010s
    by the machine learning community, it has since proven optimal or near-optimal across an
    extraordinary range of problems. The same mathematical idea that helps doctors allocate
    patients to treatments now helps Netflix recommend movies, helps ad platforms allocate
    impressions, and—as we'll see—can help AI coding assistants learn which suggestions actually
    help their users.

    What strikes me most about Thompson Sampling is its *philosophical* elegance, not just its
    mathematical elegance. Most approaches to the exploration-exploitation tradeoff require you
    to explicitly balance two competing objectives: gather information vs. maximize reward. You
    end up with tuning parameters, exploration bonuses, decaying schedules. Thompson Sampling
    sidesteps all of this. It says: *just sample your uncertainty, then act as if the sample
    were true*. That's it. Exploration emerges naturally from the width of your uncertainty.
    As you learn, uncertainty shrinks, exploitation dominates, and you never had to tune anything.

    There's a lesson here that extends beyond algorithms: sometimes the right way to handle
    uncertainty isn't to fight it or schedule around it, but to *embrace it as information*.
    Your uncertainty about the world *is* knowledge—knowledge about what you don't know. Acting
    on samples from that uncertainty turns ignorance into exploration, automatically, elegantly,
    without any explicit planning.

    ---

    ## The Concrete Problem (And the Larger Question)

    But I've gotten ahead of myself. Let me ground this in something specific—and then zoom
    back out, because the specific case opens onto a much larger question.

    **The immediate problem:** You're pair programming with an AI assistant. It suggests a
    pattern. You reject it—*that's not how we do things here*. Five minutes later, it suggests
    the same thing. The AI isn't stupid. It's **stuck**. It has no mechanism to learn from
    your corrections. Every session starts fresh.

    And the "solutions" currently on offer? I find them almost comically inadequate.

    December 2025: Sequoia publishes "AGI is 2030s, at earliest." January 2026—43 days later—they
    publish "This is AGI" and write a check at a $350 billion valuation. What changed? Not the
    technology. The narrative.

    Go read the code these narratives are built on. CrewAI's "human feedback" is flow control:
    `if feedback == "approved": route_here()`. Agno's "memory" is CRUD: get, add, update, delete.
    That's not learning. That's a key-value store with a marketing team.

    Where is the uncertainty quantification? Where are the feedback loops that update beliefs?
    Where is the mechanism that says "this rule helped, surface it again" or "this pattern keeps
    failing, deprioritize it"? Nowhere. The entire industry is building agentic systems that
    cannot learn from their own mistakes—and calling it progress.

    And the problem? You. You let them.

    - "Our agents have memory" — *it's a database with get/set*
    - "Human-in-the-loop learning" — *it's an if-statement with a modal*
    - "Continuous improvement through evals" — *evals measure; they don't teach*

    If you nodded along to any of these—don't pretend—yes, I'm talking to you—then you're
    part of how we got here. Smart people, pattern-matching on keywords, not asking "where's
    the actual learning loop?" It's fine. I did it too. But we're done now.

    The thesis papers know something is wrong. "Evals aren't enough," they say—correctly!—then
    propose solutions that amount to "what if we added more vibes to the prompt?" No regret
    bounds. No convergence guarantees. No formal model of what "learning" even means.

    Meanwhile, Sequoia's own David Cahn calculated that AI needs **$600 billion in annual
    revenue** to justify current infrastructure investment. Actual revenue: ~$100 billion.
    That's a $500 billion gap—*his* number, not mine—and nobody has shipped the learning
    machinery that might close it.

    Anyway. Back to the science.

    Here's [an actual bandit](https://github.com/peleke/buildlog-template/blob/main/src/buildlog/core/bandit.py).

    If you're reading that link thinking "what's a bandit?"—good. That's why we're here.
    By the end of this notebook, you'll know what most people importing `CrewBase` don't:
    how to build systems that actually learn from feedback, with math you can prove and
    intuition you can trust. That's the gap. This closes it.

    **buildlog** maintains a lightweight learning layer that tracks which rules help, which
    don't, and adapts—without fine-tuning the underlying model, without risking catastrophic
    forgetting, without any infrastructure beyond a local file. Thompson Sampling is the
    algorithm that makes this work.

    But here's what I want you to see: **buildlog is an instance of a much larger pattern.**

    Any system that must select among options based on uncertain, evolving evidence faces the
    same fundamental challenge. Which clinical trial arm should this patient receive? Which
    ad variant should this user see? Which API endpoint should this request route to? Which
    *rules* should this AI assistant surface to *this* developer on *this* codebase?

    The structure is identical: arms (options), rewards (outcomes), uncertainty (limited data),
    and the explore-exploit tradeoff (try new things vs. stick with what works). What changes
    is the domain—not the mathematics.

    This suggests something exciting. If we can:
    1. Formalize the learning dynamics precisely
    2. Prove properties about convergence and regret
    3. Build a reusable abstraction that captures the pattern

    ...then we haven't just built a feature for buildlog. We've built a **framework primitive**—
    a component that any agentic system could use to learn from feedback. The agent framework
    that integrates this correctly gets adaptive behavior for free: route to the right tool,
    surface the right context, select the right strategy—all learned from actual outcomes,
    not hardcoded heuristics.

    That's where this course is headed. We'll start concrete (buildlog, Thompson Sampling,
    working code) and end abstract (provable guarantees, framework integration, contribution
    to the field). The notebooks build toward a real artifact: a bandit module that ships,
    a set of experiments that demonstrate it works, and documentation rigorous enough that
    others can build on it.

    But first, we need to understand the algorithm deeply. Not just *how* it works—*why* it
    works, and why its particular form of elegance might be telling us something true about
    learning.

    By the end of this notebook, you'll:
    - Understand why "just pick the best" fails—and *why* it fails, not just *that* it fails
    - See uncertainty as a *feature*, not a bug to be eliminated
    - Build a working bandit that learns from feedback
    - Watch it outperform both random and greedy strategies
    - Have intuition for *why* sampling uncertainty leads to optimal exploration

    The mathematics is not difficult. What I hope to convey is something harder: the *sense* of
    this algorithm, why it works, and why its particular form of elegance might teach us something
    about learning more generally.

    Let's begin.
    """
    )
    return


@app.cell
def _():
    import matplotlib.pyplot as plt
    import numpy as np

    np.random.seed(42)
    return np, plt


@app.cell
def _(mo):
    mo.md(
        r"""
    ---
    # The Shape of the Problem

    ## A Thought Experiment

    Imagine you're in a city you've never visited, staying for ten nights. There are three
    restaurants within walking distance of your hotel. You know nothing about any of them.

    On your first night, you pick one at random—call it Restaurant A. The meal is good. Not
    transcendent, but solid. A 7 out of 10.

    Now it's night two. Where do you eat?

    This is not a trick question, but it is a *deep* question. The utilitarian calculus seems
    simple: you want to maximize total dining pleasure across your ten nights. But notice the
    bind you're in:

    - If you return to A, you get a predictable 7. Safe. But restaurants B and C remain mysteries.
      One of them might be a 9. You'll never know.

    - If you try B or C, you gather information—but at a cost. Tonight's meal might be a 4.
      You've sacrificed immediate reward for knowledge.

    This is the **exploration-exploitation dilemma**, and I want you to feel its teeth before
    we formalize it. The dilemma isn't artificial. Every time you choose whether to try a new
    approach or stick with what works, you're navigating this tradeoff. Every time a doctor
    chooses between a proven treatment and an experimental one, every time a scientist chooses
    between refining a known technique and testing a wild hypothesis, the same structure appears.

    The obvious strategies are obviously flawed:

    **Pure exploitation**: Return to A every night. You finish your trip never knowing that
    Restaurant C was extraordinary—a hidden gem that would have given you seven nights of 9s
    instead of 7s. You left pleasure on the table because you stopped learning too soon.

    **Pure exploration**: Rotate randomly among all three, giving each equal attention regardless
    of what you observe. By night eight you *know* C is the best, but you dutifully waste nights
    nine and ten on mediocre A and B anyway. You kept learning when you should have exploited.

    Neither extreme is rational. But what *is* the right balance? This question occupied some of
    the best minds in statistics for decades. The answer they found is surprising: there is no
    single right balance. The optimal strategy isn't a fixed ratio of exploration to exploitation.
    It's a *dynamic* policy that explores more when uncertain and exploits more when confident.

    The challenge is making "uncertain" and "confident" precise, and then acting on them correctly.
    """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ---
    # Making Abstraction Concrete

    Enough philosophy. Let's build something.

    The exploration-exploitation dilemma has a classical formalization called the **multi-armed
    bandit problem**. The name comes from slot machines ("one-armed bandits")—imagine facing a
    row of them, each with a different (unknown) payout probability. You have a finite number of
    pulls. Which machines do you play?

    The metaphor is deliberately sterile. Slot machines, unlike restaurants, have no ambiance,
    no service, no intangible qualities. They're pure reward generators, and this purity is the
    point. By stripping away everything but the essential structure—choices, rewards, uncertainty—
    we can see the problem clearly.

    We'll simulate three arms with hidden success probabilities. Think of each "pull" as a
    Bernoulli trial: success (reward = 1) or failure (reward = 0). The true probabilities are
    known to us as experimenters, but hidden from the learner. This asymmetry—between what we
    know as designers and what the algorithm knows—is crucial for building intuition about
    learning systems.
    """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ## The Setup: Three Arms, Hidden Truth

    Remember those three restaurants? Let's strip away the wine lists, the ambiance, the
    friendly waiter who remembers your name. All that matters now is a single binary
    question: *did this meal satisfy you or not?*

    Restaurant A satisfies you 30% of the time. B, 50%. C—the hidden gem—70%. But you
    don't know any of this. You walk in blind.

    | Arm | True P(success) | In restaurant terms |
    |-----|-----------------|---------------------|
    | 0   | 0.30            | Usually disappointing |
    | 1   | 0.50            | Coin flip |
    | 2   | 0.70            | **Usually great** |

    This is the asymmetry that makes learning interesting: *we* can see the truth (we're
    the experimenters, the ones running the simulation), but the algorithm is stuck inside
    the problem, learning only from what it experiences. It starts knowing nothing. Every
    meal—every pull of the arm—teaches it something. The question is whether it learns
    fast enough to matter.

    The code below defines this ground truth and a function to simulate one meal—one pull.
    Success (1) or disappointment (0), randomly, according to the hidden probabilities.
    """
    )
    return


@app.cell
def _():
    # --- THE GROUND TRUTH (hidden from the learner) ---
    TRUE_PROBS = [0.3, 0.5, 0.7]  # Arm 2 is best
    N_ARMS = len(TRUE_PROBS)
    return N_ARMS, TRUE_PROBS


@app.cell
def _(TRUE_PROBS, np):
    def pull_arm(arm_index: int) -> int:
        """Pull an arm, get a reward (1) or not (0) based on true probability."""
        return int(np.random.random() < TRUE_PROBS[arm_index])

    # Test it
    results = [pull_arm(2) for _ in range(10)]
    print(f"10 pulls of arm 2 (true prob 0.7): {results}")
    print(f"Empirical mean: {np.mean(results):.2f}")
    return (pull_arm,)


@app.cell
def _(mo):
    mo.md(
        r"""
    ## Three Baseline Strategies (And How to Keep Score)

    Before we build something smart, let's see how naive strategies fail. But first—how do
    we even measure "failing" at a learning problem?

    Here's one way: imagine an oracle who already knows Restaurant C is the best. The oracle
    eats at C every night and averages 7 out of 10 satisfaction. You, meanwhile, are stumbling
    around—night one at A (6/10), night two at B (4/10), night three back to A... By the end
    of your trip, you've accumulated less total satisfaction than the oracle. The *gap* between
    what you got and what you *could have gotten*—that's **regret**.

    You know this feeling. Three bites into a mediocre pasta, you realize you should have
    ordered the fish. That twinge? That's instant regret. Now imagine keeping a running tally
    of every suboptimal decision across your whole trip. That running tally is **cumulative regret**.

    More precisely: if the best option gives you 0.7 expected reward, and you chose something
    that gives 0.3, you just accumulated 0.4 regret for that round. Add it up over all rounds.
    Lower is better. A strategy that figures things out quickly will see its regret curve
    *flatten*—it stops making mistakes. A strategy that never learns will see regret climb
    forever, a straight line of accumulating loss.

    Now, the three naive strategies we'll race:

    1. **Random**: Pick uniformly at random. No learning at all. Pure chaos.
    2. **Greedy**: Always pick whatever *looks* best so far. Pure exploitation.
    3. **ε-Greedy**: Usually greedy, but explore randomly 10% of the time. The classic compromise.

    Let's see how they do.
    """
    )
    return


@app.cell
def _(N_ARMS, TRUE_PROBS, np, pull_arm):
    def run_strategy(strategy_fn, n_rounds: int = 500) -> dict:
        """
        Run a bandit strategy for n_rounds.

        Returns dict with:
          - choices: which arm was chosen each round
          - rewards: reward received each round
          - regret: cumulative regret over time
        """
        # Track observations for each arm
        successes = np.zeros(N_ARMS)
        failures = np.zeros(N_ARMS)

        choices = []
        rewards = []
        regrets = []
        cumulative_regret = 0.0

        best_prob = max(TRUE_PROBS)  # Optimal is always pulling the best arm

        for _ in range(n_rounds):
            # Strategy picks an arm
            arm = strategy_fn(successes, failures)

            # Pull it, get reward
            reward = pull_arm(arm)

            # Update observations
            if reward:
                successes[arm] += 1
            else:
                failures[arm] += 1

            # Track regret: what we lost vs optimal
            instant_regret = best_prob - TRUE_PROBS[arm]
            cumulative_regret += instant_regret

            choices.append(arm)
            rewards.append(reward)
            regrets.append(cumulative_regret)

        return {
            "choices": choices,
            "rewards": rewards,
            "regret": regrets,
            "final_regret": cumulative_regret,
        }

    return (run_strategy,)


@app.cell
def _(N_ARMS, np):
    # --- STRATEGY IMPLEMENTATIONS ---

    def random_strategy(successes, failures):
        """Pick uniformly at random."""
        return np.random.randint(N_ARMS)

    def greedy_strategy(successes, failures):
        """Pick the arm with highest observed success rate."""
        total = successes + failures
        # Handle cold start: if an arm has no data, give it a chance
        # Use np.divide to avoid RuntimeWarning
        rates = np.divide(
            successes, total, out=np.full_like(successes, 0.5), where=total > 0
        )
        return int(np.argmax(rates))

    def epsilon_greedy_strategy(successes, failures, epsilon=0.1):
        """Usually greedy, sometimes random."""
        if np.random.random() < epsilon:
            return np.random.randint(N_ARMS)
        return greedy_strategy(successes, failures)

    return epsilon_greedy_strategy, greedy_strategy, random_strategy


@app.cell
def _(mo):
    mo.md(
        r"""
    ## The Race: 500 Rounds, Three Strategies

    Now we run each strategy for 500 rounds and plot cumulative regret over time.
    Watch the curves: their *shape* tells you everything about how the strategy learns (or doesn't).
    """
    )
    return


@app.cell
def _(
    epsilon_greedy_strategy,
    greedy_strategy,
    np,
    plt,
    random_strategy,
    run_strategy,
):
    # Run each strategy
    np.random.seed(123)  # For reproducibility
    N_ROUNDS = 500

    random_result = run_strategy(random_strategy, N_ROUNDS)
    greedy_result = run_strategy(greedy_strategy, N_ROUNDS)
    eps_greedy_result = run_strategy(epsilon_greedy_strategy, N_ROUNDS)

    # Plot cumulative regret
    fig1, ax1 = plt.subplots(figsize=(10, 6))

    ax1.plot(random_result["regret"], label="Random", alpha=0.8, linewidth=2)
    ax1.plot(greedy_result["regret"], label="Greedy", alpha=0.8, linewidth=2)
    ax1.plot(
        eps_greedy_result["regret"], label="ε-Greedy (ε=0.1)", alpha=0.8, linewidth=2
    )

    ax1.set_xlabel("Round", fontsize=12)
    ax1.set_ylabel("Cumulative Regret", fontsize=12)
    ax1.set_title("The Cost of Bad Strategies", fontsize=14)
    ax1.legend(fontsize=11)
    ax1.grid(True, alpha=0.3)

    plt.tight_layout()
    fig1
    return (N_ROUNDS,)


@app.cell
def _(mo):
    mo.md(
        r"""
    **Reading the curves:**

    - **Random** (blue): A straight line climbing forever. No learning. The algorithm is as
      ignorant at round 500 as at round 1. This is the cost of pure exploration with no exploitation.

    - **Greedy** (orange): The outcome depends on luck. If the first few pulls happen to favor
      the best arm, greedy locks on and does well. If they favor a mediocre arm, greedy locks on
      and does *terribly*—forever. This is the cost of pure exploitation with no exploration.
      (Run the cell multiple times with different seeds to see the variance.)

    - **ε-Greedy** (green): A genuine improvement. The 10% exploration prevents catastrophic
      lock-in. But notice: the line keeps climbing, just more slowly. Even after the algorithm
      *knows* arm 2 is best, it wastes 10% of pulls on random exploration. The exploration rate
      is fixed, not adaptive. This is the cost of ad-hoc compromise.

    None of these are satisfying. We want something that explores *when uncertain* and exploits
    *when confident*—automatically, without tuning.
    """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ---
    # Uncertainty as Information

    ## The Conceptual Shift

    Here is where many treatments of this problem go wrong. They see uncertainty as an obstacle—
    a thing to be minimized, routed around, or tuned away with exploration parameters. I want to
    suggest a different view: **uncertainty is information**.

    Consider two scenarios:
    1. Arm A has succeeded 1 time out of 1 attempt. Success rate: 100%.
    2. Arm B has succeeded 70 times out of 100 attempts. Success rate: 70%.

    Which arm is better? If you answered "A, obviously—it has a higher success rate," you've
    fallen into a trap. You've thrown away information. The *point estimate* (1/1 = 100% vs
    70/100 = 70%) tells you nothing about how confident you should be in each estimate.

    What we need is not a single number summarizing each arm, but a *distribution* over possible
    values that arm's true probability might take. We need to track our full state of knowledge,
    including our ignorance.

    Enter the **Beta distribution**. Don't let the name scare you. It's just a way of keeping
    score.

    Here's the idea: instead of saying "this arm has a 70% success rate" (a single number), you
    keep *two* counters:

    - **Wins**: how many times it worked
    - **Losses**: how many times it didn't

    That's it. You're just counting. A restaurant with 7 wins and 3 losses feels different from
    a restaurant with 70 wins and 30 losses—even though both are "70%". The first one, you're
    still not sure. The second one, you *know*. The Beta distribution captures exactly this:
    not just your best guess, but *how confident you are in that guess*.

    The formula is almost insultingly simple:

    **Beta(wins + 1, losses + 1)**

    Start with 1 in each counter (that's your "I have no idea" starting point). Every time
    something works, add 1 to wins. Every time it fails, add 1 to losses. The shape of your
    belief updates automatically.

    Why the "+1"? It's a technical thing—it keeps the math well-behaved when you have no data
    yet. Don't worry about it. Just remember: **wins + 1, losses + 1**. That's your belief.

    What makes this powerful is that *uncertainty becomes visible*:
    - **Few observations** → wide, spread-out curve → "could be almost anything"
    - **Many observations** → tight, peaked curve → "I'm pretty sure it's around here"

    And here's the key: Thompson Sampling uses that *width* as a guide. Wide curve? You'll
    sample all over the place—lots of exploration. Tight curve? Your samples cluster near
    the peak—mostly exploitation. No tuning required. The math does it for you.

    (For the formally trained: yes, Beta is the conjugate prior for the Bernoulli likelihood,
    which is why the update rule is so clean. The posterior is always another Beta. If you
    know what that means, you know why this is elegant. If you don't, it doesn't matter—the
    counting version is exactly correct and you can derive everything from it.)
    """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ---
    ## Seeing Uncertainty: The Beta Distribution in Action

    We've talked about the Beta distribution as a way of keeping score. But what does a
    belief actually *look like*?

    Here's what I want you to see: a belief isn't just a number ("70% chance"). It's a
    *shape*—a curve that spreads across all the possibilities, weighted by how plausible
    each one feels given what you've observed.

    When you know nothing, what shape should that belief take? When you've seen 100
    observations, how should it change? The four panels below show this evolution.

    Two things to watch:
    - **Where the curve peaks**: your current best guess
    - **How wide it spreads**: how much you'd bet on that guess

    Both will shift as evidence accumulates. Let's watch.
    """
    )
    return


@app.cell
def _(np, plt):
    from scipy import stats

    def plot_beta(alpha, beta, ax=None, label=None, color=None):
        """Plot a Beta distribution."""
        if ax is None:
            _, ax = plt.subplots()

        x = np.linspace(0, 1, 200)
        y = stats.beta.pdf(x, alpha, beta)

        ax.plot(x, y, label=label, color=color, linewidth=2)
        ax.fill_between(x, y, alpha=0.2, color=color)
        ax.set_xlabel("Probability of Success", fontsize=11)
        ax.set_ylabel("Belief Density", fontsize=11)
        return ax

    # Show how uncertainty evolves with observations
    fig2, axes2 = plt.subplots(1, 4, figsize=(14, 3.5))

    scenarios = [
        (1, 1, "Prior: No data\nBeta(1,1)"),
        (2, 2, "1 success, 1 failure\nBeta(2,2)"),
        (8, 4, "7 successes, 3 failures\nBeta(8,4)"),
        (71, 31, "70 successes, 30 failures\nBeta(71,31)"),
    ]

    for _ax, (_a, _b, _title) in zip(axes2, scenarios):
        plot_beta(_a, _b, ax=_ax, color="steelblue")
        _ax.set_title(_title, fontsize=11)
        _ax.set_xlim(0, 1)
        _mean_val = _a / (_a + _b)
        _ax.axvline(
            _mean_val,
            color="red",
            linestyle="--",
            alpha=0.7,
            label=f"Mean: {_mean_val:.2f}",
        )
        _ax.legend(fontsize=9)

    plt.suptitle("Uncertainty Shrinks With Evidence", fontsize=13, y=1.02)
    plt.tight_layout()
    fig2
    return (stats,)


@app.cell
def _(mo):
    mo.md(
        r"""
    **Reading the shapes:**

    1. **Beta(1,1)**: Flat. Uniform. "I literally have no idea—any probability from 0 to 1 is
       equally plausible." This is the mathematically correct representation of complete ignorance.

    2. **Beta(2,2)**: After one success and one failure, the distribution peaks at 0.5 but remains
       wide. We have a *guess*, but not much *confidence*. Two data points aren't many.

    3. **Beta(8,4)**: After 10 observations (7 successes, 3 failures), the peak is near 0.7 and
       the distribution is noticeably narrower. We're starting to have an opinion.

    4. **Beta(71,31)**: After 100 observations, the distribution is tight—a spike around 0.7.
       We're *confident*. Additional observations will barely move the needle.

    This is **Bayesian inference**: start with prior beliefs, update with evidence, end with
    posterior beliefs. The machinery is mechanical; the insight is representational. By encoding
    uncertainty explicitly, we can *reason about* it—and, crucially, *act on* it.
    """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ---
    # Thompson Sampling: The Algorithm

    ## An Idea So Simple It Feels Like Cheating

    We've established that the Beta distribution encodes our uncertainty about each arm's true
    probability. Now comes Thompson's insight, published in 1933 and then inexplicably ignored
    for the better part of a century:

    **Don't compute an exploration bonus. Just sample your uncertainty and act greedily on the sample.**

    The algorithm:
    1. For each arm, draw one random sample from its Beta distribution
    2. Pick the arm whose sample came out highest
    3. Pull that arm, observe the reward
    4. Update that arm's Beta parameters (increment α if success, β if failure)
    5. Repeat

    That's it. That's the whole algorithm. There's no exploration parameter. No schedule to tune.
    No bonus terms to balance. Just: sample, act, update.

    Why does this work? The reasoning is almost philosophical:

    - If you're **uncertain** about an arm, its Beta distribution is *wide*. Samples from a wide
      distribution have high variance. Sometimes you'll sample high by chance—and that arm gets
      pulled. This is exploration, emerging naturally from uncertainty.

    - If you're **confident** about an arm (lots of data, narrow distribution), your samples
      will cluster tightly around the true mean. If that mean is high, you'll pull it consistently.
      If it's low, you'll rarely pull it. This is exploitation, emerging naturally from confidence.

    - As you **learn**, distributions narrow. The random element that drove exploration gradually
      fades, replaced by deterministic exploitation of the best arm. No decay schedule needed—
      the mathematics of Bayesian updating *is* the schedule.

    I find this deeply satisfying. Most optimization algorithms require you to manually balance
    competing objectives (explore vs. exploit), which means tuning hyperparameters, which means
    meta-optimization, which means turtles all the way down. Thompson Sampling collapses the
    two objectives into one: *act optimally given your current beliefs*. The exploration isn't
    a tax you pay for future information; it's a natural consequence of epistemic honesty about
    what you don't know.

    There's a philosophical lesson here that extends beyond bandits: perhaps the right way to
    handle uncertainty isn't to engineer around it, but to *encode it faithfully and then act
    on samples*. Your uncertainty about the world is not noise to be filtered out—it's signal
    about where to look next.
    """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ---
    ## Implementation: Thompson Sampling in Ten Lines

    The algorithm is almost disappointingly simple. For each arm, sample from its Beta posterior.
    Pick the arm with the highest sample. That's it.

    The magic is in what this *implies*: uncertain arms (wide distributions) sometimes produce
    high samples and get explored. Confident arms (narrow distributions) produce consistent
    samples near their true mean. No explicit exploration logic—just probability doing its thing.
    """
    )
    return


@app.cell
def _(N_ARMS, np):
    def thompson_sampling_strategy(successes, failures):
        """
        Thompson Sampling: sample from each arm's Beta posterior, pick highest.

        Beta parameters: alpha = 1 + successes, beta = 1 + failures
        """
        samples = []
        for arm in range(N_ARMS):
            alpha = 1 + successes[arm]
            beta = 1 + failures[arm]
            sample = np.random.beta(alpha, beta)
            samples.append(sample)

        return int(np.argmax(samples))

    return (thompson_sampling_strategy,)


@app.cell
def _(mo):
    mo.md(
        r"""
    ## The Showdown: Thompson Sampling Enters the Race

    Now we add Thompson Sampling to the competition. Same setup: 500 rounds, same three arms.
    The question: can principled uncertainty quantification beat ad-hoc exploration strategies?
    """
    )
    return


@app.cell
def _(
    N_ROUNDS,
    epsilon_greedy_strategy,
    greedy_strategy,
    np,
    plt,
    random_strategy,
    run_strategy,
    thompson_sampling_strategy,
):
    # Run Thompson Sampling alongside the others
    np.random.seed(456)

    results_random = run_strategy(random_strategy, N_ROUNDS)
    results_greedy = run_strategy(greedy_strategy, N_ROUNDS)
    results_eps = run_strategy(epsilon_greedy_strategy, N_ROUNDS)
    results_thompson = run_strategy(thompson_sampling_strategy, N_ROUNDS)

    # Plot
    fig3, ax3 = plt.subplots(figsize=(10, 6))

    ax3.plot(results_random["regret"], label="Random", alpha=0.7, linewidth=2)
    ax3.plot(results_greedy["regret"], label="Greedy", alpha=0.7, linewidth=2)
    ax3.plot(results_eps["regret"], label="ε-Greedy (ε=0.1)", alpha=0.7, linewidth=2)
    ax3.plot(
        results_thompson["regret"],
        label="Thompson Sampling",
        alpha=0.9,
        linewidth=2.5,
        color="darkgreen",
    )

    ax3.set_xlabel("Round", fontsize=12)
    ax3.set_ylabel("Cumulative Regret", fontsize=12)
    ax3.set_title("Thompson Sampling Wins", fontsize=14)
    ax3.legend(fontsize=11)
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    fig3
    return results_eps, results_greedy, results_random, results_thompson


@app.cell
def _(results_eps, results_greedy, results_random, results_thompson):
    print("Final Cumulative Regret after 500 rounds:")
    print(f"  Random:           {results_random['final_regret']:.1f}")
    print(f"  Greedy:           {results_greedy['final_regret']:.1f}")
    print(f"  ε-Greedy:         {results_eps['final_regret']:.1f}")
    print(f"  Thompson Sampling: {results_thompson['final_regret']:.1f}")
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    **Thompson Sampling (dark green) wins decisively.**

    Look at the shape: early on, regret grows (the algorithm is exploring, making "mistakes"
    to gather information). But then—crucially—the curve *flattens*. Once Thompson Sampling
    is confident that arm 2 is best, it exploits relentlessly. No wasted pulls on known-bad arms.

    Compare to ε-Greedy: even at round 500, it's still climbing. The 10% exploration tax
    is eternal. Thompson Sampling's "exploration tax" is *adaptive*—high when uncertain,
    near-zero when confident.

    This isn't just an academic comparison. This is what buildlog uses to select which rules
    to surface. Rules that help get reinforced. Rules that don't get deprioritized. And the
    algorithm figures out which is which—automatically, without hardcoded preferences, without
    manual tuning. That's the promise of principled uncertainty quantification.
    """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ---
    ## Watching Beliefs Evolve

    The regret curves showed you *that* Thompson Sampling wins. But what does it look like
    *inside the algorithm's head* as it figures this out?

    Here's something you don't get to see with most learning systems: the actual shape of
    uncertainty, updating in real time. We're about to watch three beliefs—one for each arm—
    start identical (total ignorance) and gradually separate as evidence accumulates.

    The visualization below shows six snapshots: round 0, 10, 30, 70, 150, and 199. The
    dotted vertical lines mark where the *true* probabilities are. Watch the peaks hunt
    toward truth. Watch the curves narrow as confidence grows. This is Bayesian learning,
    made visible.
    """
    )
    return


@app.cell
def _(N_ARMS, TRUE_PROBS, np, plt, pull_arm, stats):
    def run_thompson_with_history(n_rounds=200):
        """Run Thompson Sampling and record belief history."""
        successes = np.zeros(N_ARMS)
        failures = np.zeros(N_ARMS)

        history = []  # List of (round, arm, alpha, beta) for all arms

        for round_num in range(n_rounds):
            # Record current beliefs
            for arm in range(N_ARMS):
                history.append(
                    {
                        "round": round_num,
                        "arm": arm,
                        "alpha": 1 + successes[arm],
                        "beta": 1 + failures[arm],
                    }
                )

            # Thompson Sampling selection
            samples = [
                np.random.beta(1 + successes[a], 1 + failures[a]) for a in range(N_ARMS)
            ]
            chosen = int(np.argmax(samples))

            # Pull and update
            reward = pull_arm(chosen)
            if reward:
                successes[chosen] += 1
            else:
                failures[chosen] += 1

        return history, successes, failures

    np.random.seed(789)
    belief_history, final_successes, final_failures = run_thompson_with_history(200)

    # Plot beliefs at different rounds
    fig4, axes4 = plt.subplots(2, 3, figsize=(12, 7))
    rounds_to_show = [0, 10, 30, 70, 150, 199]
    colors = ["#e74c3c", "#3498db", "#2ecc71"]  # Red, Blue, Green for arms 0,1,2

    for _ax2, _show_round in zip(axes4.flat, rounds_to_show):
        _x = np.linspace(0, 1, 200)

        for _arm in range(N_ARMS):
            # Find this arm's belief at this round
            _entry = [
                h
                for h in belief_history
                if h["round"] == _show_round and h["arm"] == _arm
            ][0]
            _a2, _b2 = _entry["alpha"], _entry["beta"]
            _y = stats.beta.pdf(_x, _a2, _b2)

            _ax2.plot(
                _x,
                _y,
                color=colors[_arm],
                linewidth=2,
                label=f"Arm {_arm} (true={TRUE_PROBS[_arm]:.1f})",
            )
            _ax2.fill_between(_x, _y, alpha=0.15, color=colors[_arm])

            # Mark true probability
            _ax2.axvline(TRUE_PROBS[_arm], color=colors[_arm], linestyle=":", alpha=0.5)

        _ax2.set_title(f"Round {_show_round}", fontsize=11)
        _ax2.set_xlim(0, 1)
        _ax2.set_xlabel("P(success)")

    axes4[0, 0].legend(fontsize=9, loc="upper left")
    plt.suptitle("Thompson Sampling: Beliefs Converging to Truth", fontsize=13, y=1.02)
    plt.tight_layout()
    fig4
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    **The story the curves tell:**

    - **Round 0**: Perfect symmetry. All three arms have identical flat priors. The algorithm
      knows nothing, and its beliefs reflect that.

    - **Round 10-30**: Differentiation begins. The arms have been pulled different numbers of
      times (Thompson Sampling explores unevenly, guided by samples). Beliefs start to diverge.

    - **Round 70+**: Arm 2 (green) emerges as the clear winner. Its distribution is tight and
      centered near 0.7. The algorithm is *confident*. Meanwhile, arms 0 and 1 have been explored
      less—their distributions are tighter than at round 0, but wider than arm 2's.

    - **Round 199**: Convergence. All three distributions are tight, all centered near their true
      values. The algorithm has learned the structure of the world.

    The dotted vertical lines are the *true* probabilities. Notice how the peaks converge toward
    them. This is Bayesian inference doing what it's supposed to do: turning observations into
    accurate beliefs, with calibrated confidence.
    """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ---
    # Going Deeper: Exercises

    Understanding comes from *doing*, not just reading. The exercises below probe the edges
    of what we've built—places where the algorithm's behavior becomes interesting, non-obvious,
    or breaks down entirely. Each one teaches something the main text couldn't.
    """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ## Exercise 1: The Power of Priors

    We started every arm with Beta(1, 1)—the "I have no idea" prior. But what if you *do* have
    an idea? What if arm 2 came recommended by an expert, and you wanted to give it a head start?

    Modify the algorithm to accept **boosted priors**. Give arm 2 a prior of Beta(5, 1) instead
    of Beta(1, 1). Run the simulation. What happens?

    This isn't academic. In buildlog, "seed rules"—expert-curated axioms—get boosted priors
    precisely so they're favored early, before the system has gathered its own evidence. The
    prior encodes prior knowledge. That's the whole point.

    *Implementation hint: Pass `prior_alphas` and `prior_betas` arrays to the strategy function.*
    """
    )
    return


@app.cell
def _():
    # --- YOUR CODE HERE ---
    # def thompson_with_priors(successes, failures, prior_alphas, prior_betas):
    #     ...
    pass
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ## Exercise 2: When the World Changes

    We assumed the true probabilities are fixed. But what if they're not? What if arm 1
    becomes the best arm after round 250—the world shifts under your feet?

    This is the **non-stationary bandit** problem, and it's deeply relevant to real applications.
    User preferences drift. Code patterns evolve. The optimal choice last month may not be
    optimal today.

    Modify the simulation so TRUE_PROBS changes at round 250. Compare Thompson Sampling to ε-Greedy.
    Which adapts faster? Why?

    *Insight: Thompson Sampling never fully stops exploring—it just explores less as confidence
    grows. This "always a little uncertain" property becomes a feature, not a bug, when the
    world is non-stationary. ε-Greedy's forced 10% exploration looks less ad-hoc suddenly.*
    """
    )
    return


@app.cell
def _():
    # --- YOUR CODE HERE ---
    pass
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ## Exercise 3: The Curse of Similar Arms

    Add a 4th arm with true probability 0.65—very close to arm 2's 0.70.

    Run the simulation. What happens to regret? To the time it takes to converge?

    This exercise reveals a fundamental truth about bandits: **distinguishing similar options
    is hard**. The algorithm needs many samples to confidently separate 0.65 from 0.70. During
    that time, it's making "mistakes" that are barely mistakes at all—pulling a 0.65 arm when
    0.70 was optimal costs only 0.05 per round.

    This connects to a deep result in bandit theory: regret bounds depend on the *gaps* between
    arms. Tiny gaps → slow learning → more regret. The math makes precise what intuition suggests:
    hard problems are hard.

    *Try it: What if the 4th arm were 0.69 instead of 0.65? 0.71?*
    """
    )
    return


@app.cell
def _():
    # --- YOUR CODE HERE ---
    pass
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ---
    # Reflection: What We Built and Where We're Going

    Let's step back and consider what just happened—and where it leads.

    You implemented **Thompson Sampling**—an algorithm published in 1933, forgotten for decades,
    rediscovered around 2010, and now recognized as one of the most elegant and effective
    solutions to the exploration-exploitation problem ever devised. The same mathematical
    structure that helps doctors allocate patients to clinical trials helps your coding
    assistant learn which suggestions actually help.

    But I hope you've taken away more than an algorithm. I hope you've internalized a *way of
    thinking* about uncertainty:

    **1. Uncertainty is not the enemy.** Most engineering approaches treat uncertainty as noise
    to be minimized or ignored. The Bayesian view—which Thompson Sampling embodies—treats
    uncertainty as information. Wide distributions don't just mean "I don't know"; they mean
    "I should explore here." Narrow distributions don't just mean "I know"; they mean "I should
    exploit here." Your ignorance *guides* your learning.

    **2. The explore-exploit tradeoff dissolves when you represent beliefs correctly.** If you
    track point estimates (arm A has 70% success rate), you need explicit mechanisms to force
    exploration. If you track full distributions, exploration emerges from sampling. The dichotomy
    was an artifact of impoverished representation.

    **3. Simple algorithms can be optimal.** Thompson Sampling has been proven optimal or
    near-optimal across a remarkable range of problems. Its simplicity is not a limitation—it's
    a sign that we've found the right level of abstraction. When an algorithm is this simple and
    this good, it usually means we've understood something true about the structure of the problem.

    **4. There's a deeper reason this works—and it's geometric.** I'm planting a seed here
    that won't fully bloom until notebook 08, but I want you to carry it with you:

    Probability distributions aren't just abstract bookkeeping. They live somewhere. There's
    a space—a curved space, it turns out—where each distribution is a point, and learning is
    *movement* through that space. The Beta distributions we've been drawing? They're points
    on a manifold. Bayesian updating? That's tracing a path. Thompson Sampling? That's
    sampling directions from where you currently stand.

    The mathematics here is called *information geometry*, and it explains why "sample your
    uncertainty and act" isn't just a clever trick—it's respecting the actual shape of the
    space you're navigating. We'll get there. For now, just know: there's structure beneath
    this, and it's beautiful.

    ---

    ## The Arc of This Course

    This notebook is the first in a series. Here's where we're headed:

    | Notebook | Question | Outcome |
    |----------|----------|---------|
    | **00** (this one) | Why does "just pick the best" fail? | Working intuition for Thompson Sampling |
    | **01** | What *is* uncertainty, mathematically? | Deep understanding of Beta distributions |
    | **02** | How do beliefs update with evidence? | Bayesian inference as a computational tool |
    | **03** | Why does sampling uncertainty work? | Regret bounds, optimality proofs |
    | **04** | What if context matters? | Contextual bandits, feature-based selection |
    | **05** | How does buildlog use this? | Production integration, real feedback loops |
    | **06** | Is it actually working? | Evaluation methodology, A/B testing |
    | **07** | Can we generalize this? | Framework abstraction, contribution to the field |
    | **08** | Why does *any* of this work? | Information geometry, the manifold of beliefs |

    By the end, you won't just know how to use Thompson Sampling—you'll understand *why* it
    works, have intuition for when it breaks down, and be equipped to adapt it to new domains.
    More ambitiously: you'll have contributed to building a reusable primitive for adaptive
    learning in agentic systems.

    That's the goal. Not just learning—*building something that others can learn from*.

    ---

    ## What's Next

    In **01-uncertainty-as-superpower**, we'll go deeper on the Beta distribution itself:
    - Why Beta(1,1) is the mathematically correct "I have no idea" prior
    - How the shape parameters α and β encode sample size, confidence, and prior beliefs
    - The beautiful theory of conjugate priors, and why this particular pairing (Beta-Bernoulli)
      is no accident

    For now: **you have a working bandit**. Change the true probabilities. Watch the curves shift.
    Add a fourth arm. Make two arms nearly identical and watch the algorithm struggle to
    distinguish them. Break things. The best way to understand an algorithm is to find its limits.

    → [01-uncertainty-as-superpower.py](./01-uncertainty-as-superpower.py)
    """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    ---
    # Resources

    **This notebook**: Part of the [buildlog][repo] Thompson Sampling tutorial series.

    [repo]: https://github.com/peleke/buildlog-template

    **Theory deep-dive**: See `docs/tutorials/` for the full mathematical treatment.

    **The algorithm in production**: `src/buildlog/core/bandit.py`

    **Further reading**:
    - [A Tutorial on Thompson Sampling](https://arxiv.org/abs/1707.02038) — Russo et al., comprehensive
    - [Bandit Algorithms](https://tor-lattimore.com/downloads/book/book.pdf) — Lattimore & Szepesvári, the textbook
    """
    )
    return


if __name__ == "__main__":
    app.run()
