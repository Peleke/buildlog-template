# The Craft of Technical Writing That Teaches

> **Status**: Working draft. These principles will tighten up as buildlog's voice
> emerges through actual writing. For now, this captures patterns that *work*—not
> a style to clone wholesale, but moves to steal selectively.
>
> **Influences**: Bialek's *Biophysics*, Susskind's *Theoretical Minimum* series,
> and the general tradition of physicists who write for humans.

---

## The Core Stance

Technical writing that *teaches*—as opposed to writing that merely *documents*—requires a fundamentally different stance toward the reader. You are not explaining a tool to a user. You are inviting a mind into a way of seeing.

The goal is not information transfer. The goal is *transformation*: the reader should finish with new intuitions, not just new facts. They should be able to derive what they've learned from principles, not merely recall it.

---

## The Seven Principles

### 1. Philosophy Before Technique

Never start with "how to do X." Start with *why X exists*, what problem demanded its invention, what intellectual itch it scratches. The technique is an answer; make sure the reader feels the question first.

**Instead of:**
> "Thompson Sampling is an algorithm for multi-armed bandits that samples from posterior distributions..."

**Write:**
> "There is a beautiful tension at the heart of learning itself. To improve, you must try new things; but to perform well, you must exploit what you already know. This tension—exploration versus exploitation—sounds philosophical, and it is. But it also admits a precise mathematical treatment..."

### 2. Historical Lineage as Narrative

Ideas don't appear from nowhere. They have parents, rivals, rediscoveries. Showing this lineage accomplishes several things:
- It demonstrates that smart people struggled with this problem (the reader is in good company)
- It reveals the *contingency* of our current solutions (things could have been different)
- It honors the intellectual tradition (science as cumulative conversation)

**Example:**
> "Thompson Sampling was published in 1933 and then largely forgotten for decades. Rediscovered in the 2010s by the machine learning community, it has since proven optimal or near-optimal across an extraordinary range of problems. The same mathematical idea that helps doctors allocate patients to treatments now helps Netflix recommend movies."

### 3. Personal Voice and Intellectual Honesty

Use "I" without apology. Express genuine reactions: what surprises you, what you find beautiful, where you remain uncertain. This isn't self-indulgence—it's modeling the stance of an active thinker.

**Phrases to embrace:**
- "I find this remarkable..."
- "What strikes me most is..."
- "I believe..."
- "This isn't quite right, but it's close enough for now..."
- "Here is where many treatments go wrong..."

**Phrases to avoid:**
- "It is well known that..." (by whom? say so or don't invoke authority)
- "Obviously..." (if it were obvious, you wouldn't need to say it)
- "Simply..." (this word is almost always a lie)

### 4. Questions as Organizing Structure

The best technical writing is organized around *questions*, not topics. Each section should be answerable as a question the reader plausibly has at that moment.

**Structure a section like:**
1. Pose a question explicitly or let it emerge from the previous section
2. Explore why the obvious answers fail
3. Reveal the insight that resolves the tension
4. Show the consequences

**Example progression:**
- "Where do you eat tonight?" (the dilemma)
- "Why pure exploitation fails" (obvious answer 1 is wrong)
- "Why pure exploration fails" (obvious answer 2 is wrong)
- "The optimal strategy isn't a fixed ratio—it's dynamic" (the insight)

### 5. Concrete Before Abstract, Then Back to Concrete

Start with a vivid specific case (restaurants, slot machines, a coding assistant that won't learn). Extract the abstract principle. Then return to specifics with new eyes.

This rhythm—concrete → abstract → concrete—is the heartbeat of good technical teaching. Pure abstraction is ungrounded. Pure example is ungeneralizable. The oscillation builds both intuition and formalism.

### 6. Meta-Commentary on Learning

Occasionally step back and comment on the *learning process itself*. What should the reader take away? What's the point of this exercise? Why did you structure it this way?

**Example:**
> "I hope you've taken away more than an algorithm. I hope you've internalized a *way of thinking* about uncertainty."

This meta-level commentary helps the reader index their knowledge—they don't just learn facts, they understand what kind of facts they've learned and how to use them.

### 7. Respect the Reader's Intelligence; Serve Their Time

Assume the reader is brilliant but busy. This means:
- Don't over-explain obvious implications (respect their intelligence)
- Do explain non-obvious implications thoroughly (serve their time)
- Never pad with filler
- Every sentence should either teach something or build toward something that does

**Test:** After every paragraph, ask: "Would a smart reader resent this paragraph as a waste of their time?" If yes, cut or compress.

---

## Structural Patterns

### The Layered Reveal

For complex topics, use repeated passes at increasing depth:

```
Pass 1: Intuition (restaurant analogy)
Pass 2: Formalization (multi-armed bandit)
Pass 3: Implementation (code)
Pass 4: Visualization (plots)
Pass 5: Reflection (what did we learn?)
```

Each pass revisits the same core idea but adds resolution. The reader who stops at Pass 2 still learned something true. The reader who completes all passes has deep understanding.

### The Setup-Payoff Structure

Plant questions early that get answered later. This creates narrative momentum.

**Setup (in intro):**
> "The algorithm we'll build today sidesteps all of this. It says: *just sample your uncertainty, then act as if the sample were true*."

**Payoff (in algorithm section):**
> "Here is Thompson's insight... Don't compute an exploration bonus. Just sample your uncertainty and act greedily on the sample."

### The Discipline Bridge

When multiple fields have discovered the same idea, say so explicitly. This:
- Validates the importance of the idea
- Helps readers connect to their existing knowledge
- Models interdisciplinary thinking

**Example:**
> "...discovered and rediscovered independently by statisticians, economists, psychologists, and machine learning researchers over the past century. I find this convergence remarkable."

---

## Voice Markers

### Warmth Without Sloppiness
- Contractions are fine ("don't" not "do not")
- Conversational asides are fine ("Read that again.")
- Enthusiasm is fine ("This is beautiful.")
- Imprecision is not fine (every technical claim must be accurate)

### Confidence Without Arrogance
- State your views directly ("I believe X")
- Acknowledge uncertainty where it exists ("This isn't settled")
- Don't hedge unnecessarily ("X is perhaps arguably somewhat...")
- Don't overclaim ("This is the only way to think about...")

### Pedagogy Without Condescension
- "Let's" (collaborative, not directive)
- "Notice that..." (inviting attention, not commanding it)
- "Consider..." (offering, not requiring)
- Never "As you can clearly see..." (if they could clearly see it, you wouldn't need to say it)

---

## The Ultimate Test

After writing a section, ask:

> "Would someone who reads this be able to *derive* the key idea in a new context, or merely *recall* it in this context?"

If the answer is "recall," you've documented. If the answer is "derive," you've taught.

We're in the business of building intuition that generalizes. Facts are cheap. Understanding is precious.

---

*These principles are aspirational. No piece of writing achieves them all perfectly. But having them as a north star keeps the work honest.*
