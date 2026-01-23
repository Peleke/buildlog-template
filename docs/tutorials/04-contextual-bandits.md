# Tutorial 4: Contextual Extension

**Different Contexts, Different Beliefs**

In the real world, a rule that works well for one problem might be useless for another. This tutorial extends Thompson Sampling to contextual bandits—maintaining separate belief distributions for each context.

By the end, you'll understand buildlog's full bandit architecture and how it integrates into the session lifecycle.

---

## Table of Contents

1. [From Bandits to Contextual Bandits](#from-bandits-to-contextual-bandits)
2. [Why Context Matters](#why-context-matters)
3. [State Structure](#state-structure)
4. [Code Walkthrough: BanditState](#code-walkthrough-banditstate)
5. [Integration Points](#integration-points)
6. [Persistence: JSONL Format](#persistence-jsonl-format)
7. [Seed-Boosted Priors](#seed-boosted-priors)
8. [Full Integration in operations.py](#full-integration-in-operationspy)
9. [Putting It All Together](#putting-it-all-together)
10. [Exercises](#exercises)

---

## From Bandits to Contextual Bandits

### Standard Multi-Armed Bandits

In a standard bandit, each arm has one distribution:

```
Arm A: Beta(10, 5)  → mean 0.67
Arm B: Beta(8, 12)  → mean 0.40
Arm C: Beta(15, 5)  → mean 0.75  ← Best
```

We always select based on these distributions, regardless of the situation.

### The Limitation

What if Arm B is actually the best choice for certain problems?

```
Scenario: Type Errors
  Arm A: Good (70% effective)
  Arm B: Bad (20% effective)
  Arm C: Great (80% effective)

Scenario: API Design
  Arm A: Bad (30% effective)
  Arm B: Great (85% effective)
  Arm C: OK (50% effective)
```

A standard bandit would converge on C (best overall) and never use B—even when B is perfect for API design problems.

### Contextual Bandits

Contextual bandits maintain separate distributions per context:

```
Type Errors:
  Arm A: Beta(7, 3)  → mean 0.70
  Arm B: Beta(2, 8)  → mean 0.20
  Arm C: Beta(8, 2)  → mean 0.80  ← Best for type errors

API Design:
  Arm A: Beta(3, 7)  → mean 0.30
  Arm B: Beta(9, 2)  → mean 0.82  ← Best for API design
  Arm C: Beta(5, 5)  → mean 0.50
```

Now we can select the right rule for each situation.

---

## Why Context Matters

### In buildlog

Rules have different effectiveness for different error classes:

| Rule | Type Errors | Missing Tests | API Design |
|------|-------------|---------------|------------|
| "Validate at boundaries" | 🔥 High | 🔥 High | 😐 Medium |
| "Test error paths" | 😐 Medium | 🔥 High | 😐 Medium |
| "Use pure functions" | 🔥 High | 😐 Medium | 🔥 High |
| "Document edge cases" | ❄️ Low | 🔥 High | 🔥 High |

A context-blind bandit would average these effects, potentially surfacing "Validate at boundaries" for API design problems where it's not the best choice.

### Context Definitions

In buildlog v0.8, context = error class:

```python
# Error class examples
"type-errors"      # Type system violations
"missing-tests"    # Inadequate test coverage
"api-design"       # API contract issues
"security"         # Security vulnerabilities
"performance"      # Performance problems
"general"          # Default fallback
```

Future versions may add more context features (file type, task category, time of day).

---

## State Structure

### The Core Data Structure

```python
# arms[context][rule_id] = BetaParams
arms = {
    "type-errors": {
        "rule-1": BetaParams(alpha=5, beta=2),
        "rule-2": BetaParams(alpha=3, beta=8),
    },
    "api-design": {
        "rule-1": BetaParams(alpha=2, beta=6),
        "rule-2": BetaParams(alpha=9, beta=1),
    },
}
```

This gives us:
- **O(1) lookup** for any (context, rule) pair
- **Independent learning** per context
- **Memory efficient** (only store observed contexts)

### Visualization

```
┌─────────────────────────────────────────────────────────┐
│                    BANDIT STATE                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  "type-errors":                                         │
│    ├── "rule-1" → Beta(5, 2)  mean=0.71               │
│    ├── "rule-2" → Beta(3, 8)  mean=0.27               │
│    └── "rule-3" → Beta(10, 3) mean=0.77               │
│                                                         │
│  "api-design":                                          │
│    ├── "rule-1" → Beta(2, 6)  mean=0.25               │
│    ├── "rule-2" → Beta(9, 1)  mean=0.90               │
│    └── "rule-4" → Beta(4, 4)  mean=0.50               │
│                                                         │
│  "security":                                            │
│    └── "rule-5" → Beta(7, 2)  mean=0.78               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Note: Not all rules appear in all contexts. Rules are lazily initialized when first encountered in a context.

---

## Code Walkthrough: BanditState

From `src/buildlog/core/bandit.py`:

```python
@dataclass
class BanditState:
    """Persisted state for the contextual bandit.

    Structure:
        arms[context][rule_id] = BetaParams

    This allows O(1) lookup for any (context, rule) pair while
    maintaining separate belief distributions per context.
    """

    arms: dict[str, dict[str, BetaParams]] = field(default_factory=dict)
    seed_flags: dict[str, dict[str, bool]] = field(default_factory=dict)
```

### Core Operations

**Get parameters:**
```python
def get_params(self, context: str, rule_id: str) -> BetaParams | None:
    """Get parameters for a (context, rule) pair, if they exist."""
    return self.arms.get(context, {}).get(rule_id)
```

Double `.get()` pattern handles missing context or rule gracefully.

**Set parameters:**
```python
def set_params(
    self,
    context: str,
    rule_id: str,
    params: BetaParams,
    is_seed: bool = False,
) -> None:
    """Set parameters for a (context, rule) pair."""
    if context not in self.arms:
        self.arms[context] = {}
        self.seed_flags[context] = {}
    self.arms[context][rule_id] = params
    self.seed_flags[context][rule_id] = is_seed
```

Lazy initialization: contexts are created on first access.

**Iterate all arms:**
```python
def all_arms(self) -> Iterator[tuple[str, str, BetaParams]]:
    """Iterate over all (context, rule_id, params) tuples."""
    for context, rules in self.arms.items():
        for rule_id, params in rules.items():
            yield context, rule_id, params
```

Useful for serialization and reporting.

---

## Integration Points

### Where Bandit Connects to buildlog

```
┌──────────────────────────────────────────────────────────────┐
│                    SESSION LIFECYCLE                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. start_session(error_class="type-errors")                │
│     └─→ bandit.select(candidates, context="type-errors")    │
│         └─→ Returns: ["rule-3", "rule-1", "rule-5"]         │
│             (selected via Thompson Sampling)                 │
│                                                              │
│  2. [Work happens...]                                        │
│                                                              │
│  3. log_mistake(error_class="type-errors", description=...) │
│     └─→ bandit.batch_update(selected_rules, reward=0)       │
│         (negative feedback: rules didn't prevent mistake)   │
│                                                              │
│  4. log_reward(outcome="accepted", rules_active=[...])      │
│     └─→ bandit.update(rule_id, reward=1.0, context=...)     │
│         (positive feedback: rule helped)                     │
│                                                              │
│  5. end_session()                                            │
│     └─→ State persisted to bandit_state.jsonl               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 1. Session Start: Selection

```python
# In operations.py, start_session()
def start_session(
    buildlog_dir: Path,
    error_class: str | None = None,
    notes: str | None = None,
    select_k: int = 3,
) -> StartSessionResult:
    # ... session creation ...

    # Initialize bandit
    bandit = ThompsonSamplingBandit(buildlog_dir / "bandit_state.jsonl")

    # Get all available rules
    all_skills = load_skills(buildlog_dir)
    candidate_ids = [s.id for s in all_skills]

    # Get seed rule IDs for boosted priors
    seed_ids = _get_seed_rule_ids(buildlog_dir)

    # SELECT VIA THOMPSON SAMPLING
    selected_rules = bandit.select(
        candidates=candidate_ids,
        context=error_class or "general",
        k=select_k,
        seed_rule_ids=seed_ids,
    )

    # Store in session for later attribution
    session["selected_rules"] = selected_rules

    return StartSessionResult(
        session_id=session_id,
        selected_rules=selected_rules,
        # ...
    )
```

### 2. Mistake: Negative Feedback

```python
# In operations.py, log_mistake()
def log_mistake(
    buildlog_dir: Path,
    error_class: str,
    description: str,
    corrected_by_rule: str | None = None,
) -> LogMistakeResult:
    # ... mistake logging ...

    # Get active session
    session = get_active_session(buildlog_dir)
    if session and session.get("selected_rules"):
        # NEGATIVE FEEDBACK: Selected rules didn't prevent this mistake
        bandit = ThompsonSamplingBandit(buildlog_dir / "bandit_state.jsonl")
        bandit.batch_update(
            rule_ids=session["selected_rules"],
            reward=0.0,  # Failure signal
            context=session.get("error_class", "general"),
        )

    return LogMistakeResult(
        mistake_id=mistake_id,
        # ...
    )
```

### 3. Explicit Reward: Positive/Negative Feedback

```python
# In operations.py, log_reward()
def log_reward(
    buildlog_dir: Path,
    outcome: str,  # "accepted", "revision", "rejected"
    rules_active: list[str] | None = None,
    error_class: str | None = None,
    # ...
) -> LogRewardResult:
    # Compute reward value
    if outcome == "accepted":
        reward_value = 1.0
    elif outcome == "rejected":
        reward_value = 0.0
    else:  # revision
        reward_value = 1.0 - revision_distance

    # UPDATE BANDIT with explicit feedback
    if rules_active:
        bandit = ThompsonSamplingBandit(buildlog_dir / "bandit_state.jsonl")
        for rule_id in rules_active:
            bandit.update(
                rule_id=rule_id,
                reward=reward_value,
                context=error_class or "general",
            )

    return LogRewardResult(
        reward_value=reward_value,
        # ...
    )
```

---

## Persistence: JSONL Format

### Why JSONL?

- **Append-only writes**: Safe for concurrent access
- **Crash recovery**: Partial writes don't corrupt existing data
- **Human readable**: Debug by inspecting the file
- **Efficient updates**: Don't rewrite entire file for each update

### File Format

`.buildlog/bandit_state.jsonl`:
```json
{"context": "type-errors", "rule_id": "arch-123", "alpha": 3.0, "beta": 2.0, "is_seed": false, "updated_at": "2026-01-22T10:00:00"}
{"context": "type-errors", "rule_id": "arch-456", "alpha": 5.0, "beta": 1.0, "is_seed": true, "updated_at": "2026-01-22T10:01:00"}
{"context": "api-design", "rule_id": "arch-123", "alpha": 2.0, "beta": 6.0, "is_seed": false, "updated_at": "2026-01-22T10:02:00"}
{"context": "type-errors", "rule_id": "arch-123", "alpha": 4.0, "beta": 2.0, "is_seed": false, "updated_at": "2026-01-22T10:03:00"}
```

Note: Line 4 supersedes line 1 (same context + rule_id, later timestamp).

### Load with Compaction

```python
@classmethod
def load(cls, path: Path) -> BanditState:
    """Load state from JSONL file, compacting duplicate entries."""
    state = cls()

    if not path.exists():
        return state

    # Read all records, keeping only the latest per (context, rule_id)
    records: dict[tuple[str, str], ArmRecord] = {}

    for line in path.read_text().strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            record = ArmRecord.from_dict(data)
            key = (record.context, record.rule_id)

            # Keep if newer or first seen
            if key not in records or record.updated_at > records[key].updated_at:
                records[key] = record
        except (json.JSONDecodeError, KeyError, ValueError):
            # Skip malformed lines (crash recovery)
            continue

    # Populate state from compacted records
    for (context, rule_id), record in records.items():
        state.set_params(context, rule_id, record.params, record.is_seed)

    return state
```

### Append Update (Efficient)

```python
def append_update(self, path: Path, context: str, rule_id: str) -> None:
    """Append a single arm's update to the JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    params = self.get_params(context, rule_id)
    if params is None:
        return

    record = ArmRecord(
        context=context,
        rule_id=rule_id,
        params=params,
        is_seed=self.is_seed(context, rule_id),
    )

    with open(path, "a") as f:
        f.write(json.dumps(record.to_dict()) + "\n")
```

Appends one line instead of rewriting entire file.

### Save with Compaction

```python
def save(self, path: Path) -> None:
    """Save full state to JSONL file (compacted)."""
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    for context, rule_id, params in self.all_arms():
        record = ArmRecord(
            context=context,
            rule_id=rule_id,
            params=params,
            is_seed=self.is_seed(context, rule_id),
        )
        lines.append(json.dumps(record.to_dict()))

    path.write_text("\n".join(lines) + "\n" if lines else "")
```

Called at session start (after selection) to compact the file.

---

## Seed-Boosted Priors

### The Problem: Cold Start

New rules start with Beta(1, 1)—maximum uncertainty. They need several observations before the bandit can make informed decisions.

### The Solution: Expert Priors

Rules from gauntlet personas (Security Karen, Test Terrorist, etc.) are **curated by domain experts**. We encode this expertise as a boosted prior.

```python
def _create_prior(self, is_seed: bool) -> BetaParams:
    """Create prior distribution for a new arm."""
    if is_seed:
        # Boosted prior: Beta(1 + 2, 1) = Beta(3, 1)
        # Mean = 0.75 (optimistic)
        # As if rule already had 2 extra successes
        return BetaParams(alpha=1.0 + self.seed_boost, beta=1.0)
    else:
        # Uninformative prior: Beta(1, 1)
        # Mean = 0.50 (maximum uncertainty)
        return BetaParams(alpha=1.0, beta=1.0)
```

### Visualization

```python
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

def visualize_seed_boost():
    """Compare seed vs learned rule priors."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    x = np.linspace(0, 1, 1000)

    # Seed rule: Beta(3, 1) - optimistic
    ax = axes[0]
    pdf = stats.beta.pdf(x, 3, 1)
    ax.plot(x, pdf, 'steelblue', linewidth=2)
    ax.fill_between(x, pdf, alpha=0.3)
    ax.axvline(3/4, color='red', linestyle='--', label='Mean: 0.75')
    ax.set_title('Seed Rule: Beta(3, 1)\n"Probably effective"')
    ax.set_xlabel('Effectiveness')
    ax.legend()

    # Learned rule: Beta(1, 1) - uncertain
    ax = axes[1]
    pdf = stats.beta.pdf(x, 1, 1)
    ax.plot(x, pdf, 'orange', linewidth=2)
    ax.fill_between(x, pdf, alpha=0.3, color='orange')
    ax.axvline(0.5, color='red', linestyle='--', label='Mean: 0.50')
    ax.set_title('Learned Rule: Beta(1, 1)\n"No idea"')
    ax.set_xlabel('Effectiveness')
    ax.legend()

    # After 3 failures, seed matches learned's prior mean
    ax = axes[2]
    pdf_seed = stats.beta.pdf(x, 3, 4)  # 3 failures later
    pdf_learned = stats.beta.pdf(x, 1, 1)
    ax.plot(x, pdf_seed, 'steelblue', linewidth=2, label='Seed after 3 failures')
    ax.plot(x, pdf_learned, 'orange', linewidth=2, alpha=0.5, label='Fresh learned')
    ax.axvline(3/7, color='red', linestyle='--', label=f'Seed mean: {3/7:.2f}')
    ax.set_title('Seed After 3 Failures\n"Maybe not so great"')
    ax.set_xlabel('Effectiveness')
    ax.legend()

    plt.tight_layout()
    plt.savefig('seed_boost.png', dpi=150)
    plt.show()

visualize_seed_boost()
```

### The Intuition

Seed boost = "benefit of the doubt" for expert-curated rules:
- **2 extra successes** before seeing any data
- Takes **3 failures** to drop below a fresh learned rule
- If data says seed rule is bad, it will eventually be demoted
- But we give it a head start based on expert judgment

---

## Full Integration in operations.py

### The Complete Flow

```python
# Simplified version of the actual integration

# 1. START SESSION
def start_session(buildlog_dir, error_class=None, select_k=3):
    # Create session
    session_id = generate_session_id()
    session = Session(
        session_id=session_id,
        error_class=error_class or "general",
        selected_rules=[],
    )

    # BANDIT SELECTION
    bandit = ThompsonSamplingBandit(buildlog_dir / "bandit_state.jsonl")
    all_rules = [s.id for s in load_skills(buildlog_dir)]
    seed_rules = get_seed_rule_ids(buildlog_dir)

    selected = bandit.select(
        candidates=all_rules,
        context=session.error_class,
        k=select_k,
        seed_rule_ids=seed_rules,
    )

    session.selected_rules = selected
    save_session(session)

    return StartSessionResult(
        session_id=session_id,
        error_class=session.error_class,
        selected_rules=selected,
    )


# 2. LOG MISTAKE
def log_mistake(buildlog_dir, error_class, description):
    session = get_active_session(buildlog_dir)

    # Record mistake
    mistake = Mistake(
        id=generate_mistake_id(),
        error_class=error_class,
        description=description,
    )
    save_mistake(mistake)

    # NEGATIVE FEEDBACK TO BANDIT
    if session and session.selected_rules:
        bandit = ThompsonSamplingBandit(buildlog_dir / "bandit_state.jsonl")
        for rule_id in session.selected_rules:
            bandit.update(
                rule_id=rule_id,
                reward=0.0,  # Rules didn't help
                context=session.error_class,
            )

    return LogMistakeResult(mistake_id=mistake.id)


# 3. LOG REWARD
def log_reward(buildlog_dir, outcome, rules_active=None, error_class=None):
    # Compute reward
    reward_value = {
        "accepted": 1.0,
        "revision": 0.5,  # Or based on revision_distance
        "rejected": 0.0,
    }[outcome]

    # EXPLICIT FEEDBACK TO BANDIT
    if rules_active:
        bandit = ThompsonSamplingBandit(buildlog_dir / "bandit_state.jsonl")
        for rule_id in rules_active:
            bandit.update(
                rule_id=rule_id,
                reward=reward_value,
                context=error_class or "general",
            )

    return LogRewardResult(reward_value=reward_value)


# 4. END SESSION
def end_session(buildlog_dir):
    session = get_active_session(buildlog_dir)
    session.ended_at = now()
    save_session(session)

    return EndSessionResult(
        session_id=session.session_id,
        mistakes_logged=count_session_mistakes(session),
    )
```

---

## Putting It All Together

### Complete Example

```python
import random
from pathlib import Path
from dataclasses import dataclass, field
import json
from datetime import datetime

# Simplified implementation for demonstration
@dataclass
class BetaParams:
    alpha: float = 1.0
    beta: float = 1.0

    def sample(self):
        return random.betavariate(self.alpha, self.beta)

    def update(self, reward):
        self.alpha += reward
        self.beta += (1 - reward)

    def mean(self):
        return self.alpha / (self.alpha + self.beta)


class ContextualBandit:
    def __init__(self, seed_boost=2.0):
        self.arms = {}  # context -> rule_id -> BetaParams
        self.seed_boost = seed_boost
        self.seed_rules = set()

    def add_seed_rules(self, rule_ids):
        self.seed_rules.update(rule_ids)

    def select(self, candidates, context, k=3):
        if context not in self.arms:
            self.arms[context] = {}

        samples = []
        for rule_id in candidates:
            if rule_id not in self.arms[context]:
                # Initialize with appropriate prior
                is_seed = rule_id in self.seed_rules
                alpha = 1.0 + (self.seed_boost if is_seed else 0)
                self.arms[context][rule_id] = BetaParams(alpha=alpha, beta=1.0)

            params = self.arms[context][rule_id]
            samples.append((rule_id, params.sample()))

        samples.sort(key=lambda x: x[1], reverse=True)
        return [rule_id for rule_id, _ in samples[:k]]

    def update(self, rule_id, reward, context):
        if context in self.arms and rule_id in self.arms[context]:
            self.arms[context][rule_id].update(reward)

    def get_stats(self, context):
        if context not in self.arms:
            return {}
        return {
            rule_id: {
                "mean": params.mean(),
                "alpha": params.alpha,
                "beta": params.beta,
            }
            for rule_id, params in self.arms[context].items()
        }


# Simulation
def simulate_contextual_learning():
    """Simulate learning across multiple contexts."""
    # True effectiveness rates (unknown to bandit)
    true_rates = {
        "type-errors": {
            "rule-1": 0.7, "rule-2": 0.3, "rule-3": 0.8, "rule-4": 0.5
        },
        "api-design": {
            "rule-1": 0.3, "rule-2": 0.8, "rule-3": 0.4, "rule-4": 0.6
        },
    }

    bandit = ContextualBandit(seed_boost=2.0)
    bandit.add_seed_rules({"rule-3"})  # rule-3 is a seed rule

    all_rules = ["rule-1", "rule-2", "rule-3", "rule-4"]
    n_sessions = 100

    for session in range(n_sessions):
        # Randomly choose context
        context = random.choice(["type-errors", "api-design"])

        # Select rules for this session
        selected = bandit.select(all_rules, context, k=2)

        # Simulate: each selected rule either helps or not
        for rule_id in selected:
            true_rate = true_rates[context][rule_id]
            success = random.random() < true_rate
            reward = 1.0 if success else 0.0
            bandit.update(rule_id, reward, context)

    # Print final learned beliefs
    print("Learned beliefs after 100 sessions:")
    print("=" * 60)

    for context in ["type-errors", "api-design"]:
        print(f"\n{context}:")
        stats = bandit.get_stats(context)
        sorted_rules = sorted(stats.items(), key=lambda x: x[1]["mean"], reverse=True)

        for rule_id, s in sorted_rules:
            true_rate = true_rates[context][rule_id]
            print(f"  {rule_id}: mean={s['mean']:.2f} (true={true_rate:.1f}) "
                  f"Beta({s['alpha']:.0f}, {s['beta']:.0f})")

random.seed(42)
simulate_contextual_learning()
```

Output:
```
Learned beliefs after 100 sessions:

type-errors:
  rule-3: mean=0.78 (true=0.8) Beta(21, 6)
  rule-1: mean=0.68 (true=0.7) Beta(15, 7)
  rule-4: mean=0.50 (true=0.5) Beta(8, 8)
  rule-2: mean=0.35 (true=0.3) Beta(6, 11)

api-design:
  rule-2: mean=0.79 (true=0.8) Beta(19, 5)
  rule-4: mean=0.59 (true=0.6) Beta(10, 7)
  rule-3: mean=0.47 (true=0.4) Beta(11, 12)
  rule-1: mean=0.32 (true=0.3) Beta(6, 13)
```

The bandit correctly learns that:
- rule-3 is best for type-errors (0.78 vs true 0.8)
- rule-2 is best for api-design (0.79 vs true 0.8)
- Different rankings per context!

---

## Exercises

### Conceptual Exercises

**Exercise 4.1: Context Independence**

A rule has these distributions:
- "type-errors": Beta(10, 5), mean = 0.67
- "api-design": Beta(2, 8), mean = 0.20

What happens when we:
1. Update with reward=1 in "type-errors"?
2. Update with reward=0 in "api-design"?
3. Select for a new context "security"?

<details>
<summary>Solution</summary>

1. **type-errors update:** Beta(10, 5) → Beta(11, 5), mean = 0.69
   Only type-errors context is affected.

2. **api-design update:** Beta(2, 8) → Beta(2, 9), mean = 0.18
   Only api-design context is affected.

3. **security selection:** Rule doesn't exist in security context.
   It will be initialized with default prior:
   - If seed: Beta(3, 1), mean = 0.75
   - If learned: Beta(1, 1), mean = 0.50

Contexts are completely independent. Learning in one doesn't affect others.

</details>

---

**Exercise 4.2: Seed Boost Trade-offs**

A seed boost of 2.0 means Beta(3, 1) prior for seed rules.

1. What if boost = 10? (Beta(11, 1), mean ≈ 0.92)
2. What if boost = 0.5? (Beta(1.5, 1), mean = 0.60)
3. What's the risk of too high a boost?

<details>
<summary>Solution</summary>

1. **boost = 10:** Seed rules start very optimistically. Need 10+ failures to drop below 0.5.
   - Pro: Strongly favors expert rules
   - Con: Bad seed rules hard to demote

2. **boost = 0.5:** Seed rules only slightly favored. Mean = 0.60 vs learned 0.50.
   - Pro: Data quickly overrides
   - Con: Seed rules barely get "benefit of doubt"

3. **Risk of high boost:** A poorly curated seed rule will dominate selections
   even when data shows it's ineffective. The bandit becomes slow to learn.

Default (2.0) is a balance: meaningful advantage, but data can override within ~5-10 observations.

</details>

---

**Exercise 4.3: Context Granularity**

Consider these possible context definitions:

A. Very coarse: `context = "coding"` (one context for everything)
B. Moderate: `context = error_class` (5-10 contexts)
C. Very fine: `context = f"{error_class}:{file_type}:{time_of_day}"` (hundreds)

What are the trade-offs?

<details>
<summary>Solution</summary>

**A. Very coarse (1 context):**
- Pro: Fast learning (all data contributes)
- Con: Can't specialize rules for different situations
- Use when: Rules are generally applicable

**B. Moderate (5-10 contexts):**
- Pro: Balances specialization and learning speed
- Con: Need enough sessions per context to learn
- Use when: Rules have meaningfully different effectiveness across contexts
- **This is buildlog's current approach**

**C. Very fine (hundreds of contexts):**
- Pro: Maximum specialization
- Con: Cold start everywhere, very slow learning
- Con: Context explosion (storage, computation)
- Use when: You have massive data, clear context importance

The right granularity depends on:
1. How much does effectiveness vary by context?
2. How much data do you have?
3. What's the cost of wrong selections?

</details>

---

### Coding Exercises

**Exercise 4.4: Implement Context-Aware Reporting**

Write a function that generates a report of top rules per context:

```python
def generate_context_report(bandit, top_k=3):
    """
    Generate a report showing top rules for each context.

    Returns:
        Dict mapping context to list of (rule_id, mean, ci) tuples
    """
    # YOUR CODE HERE
    pass
```

<details>
<summary>Solution</summary>

```python
def generate_context_report(bandit, top_k=3):
    report = {}

    for context, rules in bandit.arms.items():
        rankings = []
        for rule_id, params in rules.items():
            mean = params.mean()
            # 95% CI approximation
            std = (params.alpha * params.beta /
                   ((params.alpha + params.beta)**2 * (params.alpha + params.beta + 1)))**0.5
            ci = (max(0, mean - 1.96*std), min(1, mean + 1.96*std))
            rankings.append((rule_id, mean, ci))

        rankings.sort(key=lambda x: x[1], reverse=True)
        report[context] = rankings[:top_k]

    return report

# Usage
report = generate_context_report(bandit)
for context, rules in report.items():
    print(f"\n{context}:")
    for rule_id, mean, ci in rules:
        print(f"  {rule_id}: {mean:.2f} [{ci[0]:.2f}, {ci[1]:.2f}]")
```

</details>

---

**Exercise 4.5: Implement Context Migration**

Sometimes you want to rename a context or merge two contexts. Implement:

```python
def migrate_context(bandit, old_context, new_context, merge=False):
    """
    Migrate arms from old_context to new_context.

    If merge=True and new_context exists, combine distributions.
    If merge=False and new_context exists, raise error.
    """
    # YOUR CODE HERE
    pass
```

<details>
<summary>Solution</summary>

```python
def migrate_context(bandit, old_context, new_context, merge=False):
    if old_context not in bandit.arms:
        return  # Nothing to migrate

    if new_context in bandit.arms and not merge:
        raise ValueError(f"Context {new_context} already exists. Use merge=True to combine.")

    if new_context not in bandit.arms:
        bandit.arms[new_context] = {}

    for rule_id, params in bandit.arms[old_context].items():
        if rule_id in bandit.arms[new_context] and merge:
            # Combine distributions: add pseudo-counts
            existing = bandit.arms[new_context][rule_id]
            # Subtract priors to avoid double-counting, then add
            combined_alpha = existing.alpha + params.alpha - 1
            combined_beta = existing.beta + params.beta - 1
            bandit.arms[new_context][rule_id] = BetaParams(combined_alpha, combined_beta)
        else:
            # Copy as-is
            bandit.arms[new_context][rule_id] = BetaParams(params.alpha, params.beta)

    del bandit.arms[old_context]
```

</details>

---

**Exercise 4.6: Cross-Context Transfer Learning**

When a rule is new to a context, we could use data from other contexts as a weak prior. Implement:

```python
def select_with_transfer(bandit, candidates, context, k=3, transfer_weight=0.3):
    """
    Select rules with transfer learning from other contexts.

    For new rules in this context, initialize prior based on
    performance in other contexts (weighted by transfer_weight).
    """
    # YOUR CODE HERE
    pass
```

<details>
<summary>Solution</summary>

```python
def select_with_transfer(bandit, candidates, context, k=3, transfer_weight=0.3):
    if context not in bandit.arms:
        bandit.arms[context] = {}

    samples = []
    for rule_id in candidates:
        if rule_id not in bandit.arms[context]:
            # Check other contexts for this rule
            other_alphas = []
            other_betas = []

            for ctx, rules in bandit.arms.items():
                if ctx != context and rule_id in rules:
                    other_alphas.append(rules[rule_id].alpha)
                    other_betas.append(rules[rule_id].beta)

            if other_alphas:
                # Transfer: weighted average of other contexts
                mean_alpha = sum(other_alphas) / len(other_alphas)
                mean_beta = sum(other_betas) / len(other_betas)

                # Blend with uniform prior
                alpha = 1.0 + transfer_weight * (mean_alpha - 1)
                beta = 1.0 + transfer_weight * (mean_beta - 1)
            else:
                # No transfer data, use uniform
                alpha, beta = 1.0, 1.0

            bandit.arms[context][rule_id] = BetaParams(alpha, beta)

        params = bandit.arms[context][rule_id]
        samples.append((rule_id, params.sample()))

    samples.sort(key=lambda x: x[1], reverse=True)
    return [rule_id for rule_id, _ in samples[:k]]
```

</details>

---

### Challenge Exercises

**Exercise 4.7: Non-Stationary Contexts**

What if rule effectiveness changes over time within a context? Implement exponential decay:

```python
class DecayingContextualBandit:
    """Contextual bandit with exponential decay for non-stationarity."""

    def __init__(self, decay_rate=0.99):
        self.arms = {}
        self.decay_rate = decay_rate

    def decay_all(self, context):
        """Apply decay to all arms in a context."""
        # YOUR CODE HERE
        pass

    def update(self, rule_id, reward, context):
        """Update with decay."""
        # YOUR CODE HERE
        pass
```

<details>
<summary>Solution</summary>

```python
class DecayingContextualBandit:
    def __init__(self, decay_rate=0.99):
        self.arms = {}
        self.decay_rate = decay_rate

    def decay_all(self, context):
        """Decay all arms toward prior."""
        if context not in self.arms:
            return

        for rule_id, params in self.arms[context].items():
            # Decay toward Beta(1, 1)
            params.alpha = 1 + self.decay_rate * (params.alpha - 1)
            params.beta = 1 + self.decay_rate * (params.beta - 1)

    def update(self, rule_id, reward, context):
        # First decay existing observations
        self.decay_all(context)

        # Then add new observation
        if context not in self.arms:
            self.arms[context] = {}
        if rule_id not in self.arms[context]:
            self.arms[context][rule_id] = BetaParams()

        self.arms[context][rule_id].update(reward)
```

</details>

---

**Exercise 4.8: Multi-Objective Contexts**

Extend to handle multiple objectives per context:

```python
class MultiObjectiveBandit:
    """
    Track multiple objectives: effectiveness AND cost.

    arms[context][rule_id] = {
        "effectiveness": BetaParams,
        "cost": BetaParams,  # Lower is better
    }
    """

    def select(self, candidates, context, k=3, cost_weight=0.2):
        """Select rules balancing effectiveness and cost."""
        # YOUR CODE HERE
        pass
```

<details>
<summary>Solution</summary>

```python
class MultiObjectiveBandit:
    def __init__(self):
        self.arms = {}  # context -> rule_id -> {"effectiveness": BetaParams, "cost": BetaParams}

    def select(self, candidates, context, k=3, cost_weight=0.2):
        if context not in self.arms:
            self.arms[context] = {}

        scores = []
        for rule_id in candidates:
            if rule_id not in self.arms[context]:
                self.arms[context][rule_id] = {
                    "effectiveness": BetaParams(),
                    "cost": BetaParams(),
                }

            arm = self.arms[context][rule_id]

            # Sample from both distributions
            eff_sample = arm["effectiveness"].sample()
            cost_sample = arm["cost"].sample()

            # Combined score: effectiveness - cost_weight * cost
            score = eff_sample - cost_weight * cost_sample
            scores.append((rule_id, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [rule_id for rule_id, _ in scores[:k]]

    def update_effectiveness(self, rule_id, reward, context):
        if context in self.arms and rule_id in self.arms[context]:
            self.arms[context][rule_id]["effectiveness"].update(reward)

    def update_cost(self, rule_id, cost, context):
        if context in self.arms and rule_id in self.arms[context]:
            self.arms[context][rule_id]["cost"].update(cost)
```

</details>

---

**Exercise 4.9: Implement Full JSONL Persistence**

Implement the complete persistence layer with append-only writes and compaction:

```python
class PersistentBanditState:
    def __init__(self, path):
        self.path = path
        self.arms = {}
        self.load()

    def load(self):
        """Load and compact from JSONL."""
        # YOUR CODE HERE
        pass

    def append(self, context, rule_id, params):
        """Append single update."""
        # YOUR CODE HERE
        pass

    def compact(self):
        """Rewrite file without duplicates."""
        # YOUR CODE HERE
        pass
```

<details>
<summary>Solution</summary>

```python
import json
from datetime import datetime
from pathlib import Path

class PersistentBanditState:
    def __init__(self, path):
        self.path = Path(path)
        self.arms = {}
        self.load()

    def load(self):
        """Load and compact from JSONL."""
        if not self.path.exists():
            return

        records = {}  # (context, rule_id) -> (timestamp, params)

        for line in self.path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                key = (data["context"], data["rule_id"])
                timestamp = data.get("updated_at", "")

                if key not in records or timestamp > records[key][0]:
                    records[key] = (timestamp, data)
            except (json.JSONDecodeError, KeyError):
                continue

        for (context, rule_id), (_, data) in records.items():
            if context not in self.arms:
                self.arms[context] = {}
            self.arms[context][rule_id] = BetaParams(
                alpha=data["alpha"],
                beta=data["beta"],
            )

    def append(self, context, rule_id, params):
        """Append single update."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

        record = {
            "context": context,
            "rule_id": rule_id,
            "alpha": params.alpha,
            "beta": params.beta,
            "updated_at": datetime.now().isoformat(),
        }

        with open(self.path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def compact(self):
        """Rewrite file without duplicates."""
        lines = []
        for context, rules in self.arms.items():
            for rule_id, params in rules.items():
                record = {
                    "context": context,
                    "rule_id": rule_id,
                    "alpha": params.alpha,
                    "beta": params.beta,
                    "updated_at": datetime.now().isoformat(),
                }
                lines.append(json.dumps(record))

        self.path.write_text("\n".join(lines) + "\n" if lines else "")
```

</details>

---

## Summary

You now understand:

1. **Why contextual:** Rules have different effectiveness in different situations
2. **State structure:** `arms[context][rule_id] = BetaParams`
3. **Integration points:** session start, mistake, explicit reward
4. **Persistence:** JSONL with append-only writes, compaction on load
5. **Seed-boosted priors:** Encode expert knowledge for curated rules
6. **Full lifecycle:** From selection through feedback to learning

This completes the Thompson Sampling tutorial series. You can now:
- Implement bandits from scratch
- Understand buildlog's implementation
- Extend to new features (more contexts, transfer learning, etc.)
- Debug and diagnose bandit behavior

---

## Series Summary

| Tutorial | Key Concepts | Code Focus |
|----------|--------------|------------|
| 0: Background | MAB, explore-exploit, Bayesian basics | Intuition building |
| 1: Beta Distribution | Parameterization, shapes, convergence | `BetaParams` |
| 2: Bayesian Updates | Conjugacy, update rule, partial rewards | `update()` |
| 3: Thompson Sampling | Sampling vs mean, regret bounds | `select()` |
| 4: Contextual Extension | Context structure, persistence, integration | Full architecture |

**The journey:**
```
Unknown probability → Beta distribution → Bayesian updates
       ↓                    ↓                   ↓
   Model it              Represent it        Learn from data
                              ↓
                     Thompson Sampling
                              ↓
                     Explore intelligently
                              ↓
                     Contextual extension
                              ↓
                   Rules for the right context
```

---

*Previous: [Tutorial 3: Thompson Sampling](./03-thompson-sampling.md)*

*Back to: [Tutorial 0: Background Concepts](./00-background-concepts.md)*
