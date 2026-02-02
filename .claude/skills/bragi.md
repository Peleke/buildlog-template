---
name: bragi
description: Scan markdown files for LLM-ish prose patterns and suggest concrete rewrites
user_invocable: true
---

# bragi: LLM prose pattern review

Scan the specified markdown file(s) for LLM-ish prose patterns. For each match, report the line number, the pattern name, the offending text, and a concrete rewrite suggestion.

## Patterns to detect

1. **Em-dash usage** : any use of em dashes. LLMs deploy them constantly and poorly. *Fix: use colons, semicolons, commas, parentheses, or separate sentences.*
2. **Dismissive 'with' framing** : "A demo with persistence" minimizing significant features. *Fix: give the feature its own sentence or clause weight.*
3. **Tricolon/five-item enumerations** : rhythmic clause lists ("fast, reliable, scalable"). *Fix: keep only the items that earn their place; drop filler.*
4. **Performative honesty** : "Being honest:", "To be frank:" *Fix: delete the preamble; just state the thing.*
5. **Self-referential pivot** : "This is where X diverges..." narrating your own argument. *Fix: make the point without announcing it.*
6. **Punchy fragment marketing copy** : sentence fragments styled as slogans. *Fix: complete the sentence with a concrete claim.*
7. **Colon-into-bold-statement** : "The question: **...**" formatting crutch. *Fix: integrate the statement into the paragraph.*
8. **Rhythmic parallel construction closers** : participial phrase chains as paragraph endings. *Fix: end with one concrete, specific claim.*
9. **Hedging with 'not' lists** : "Not X. Not Y. Not Z." staccato negation. *Fix: say what it is, not what it isn't.*

## Instructions

1. Read the target file(s).
2. For each pattern match, output:
   - `L{line}: [{pattern name}]` the offending text (quoted)
   - Three ranked rewrite options, labeled `1.` (best) through `3.`. Each must avoid the flagged pattern while preserving the author's intent. Vary the approach: restructure, simplify, or reframe. Do not converge on the same fix three times.
3. Preserve the author's voice. The goal is to strip LLM-isms, not rewrite into a different LLM style. Keep the substance; fix the packaging.
4. If a passage has no issues, skip it. Don't flag things that aren't there.
5. At the end, provide a summary count: `{n} patterns found across {m} lines`.

## Example output

```
L14: [Em-dash usage] "Not a template, a system"
  1. "buildlog is a system, not a template."
  2. "buildlog is a system for capturing structured work trajectories."
  3. "This is a system. Templates don't learn."

L27: [Performative honesty] "Being honest about where things are:"
  1. (delete the preamble; the list speaks for itself)
  2. "Current status:"
  3. "Known limitations:"

L45: [Tricolon enumeration] "They execute, improvise, and forget"
  1. "They execute without retaining context."
  2. "They execute, then start over. Every session is session zero."
  3. "Each session starts from scratch with the same blind spots."

3 patterns found across 3 lines.
```
