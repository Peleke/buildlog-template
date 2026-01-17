#!/usr/bin/env python3
"""Post-generation script to update CLAUDE.md with buildlog instructions."""

from pathlib import Path

CLAUDE_MD_SECTION = """
## Build Journal

After completing significant work (features, debugging sessions, deployments,
2+ hour focused sessions), write a build journal entry.

**Location:** `buildlog/YYYY-MM-DD-{slug}.md`
**Template:** `buildlog/_TEMPLATE.md`

### Required Sections
1. **The Goal** - What we built and why
2. **What We Built** - Architecture diagram, components table
3. **The Journey** - Chronological INCLUDING mistakes, wrong turns, actual errors
4. **Test Results** - Actual commands run, actual outputs received
5. **Code Samples** - Key snippets with context (not full files)
6. **AI Experience Reflection** - Meta-commentary on the collaboration
7. **Improvements** - Actionable learnings: architectural, workflow, tool usage

The **Improvements** section is critical - capture concrete insights like
"Should have defined the API contract before implementing the client"
not vague observations like "Should have planned better."

**Quality bar:** Publishable as a $500+ Envato Tuts+/Manning tutorial.

After significant work, ask: "Should I write a build journal entry for this?"
"""


def main():
    claude_md = Path("CLAUDE.md")

    if not claude_md.exists():
        print("No CLAUDE.md found, skipping update")
        return

    content = claude_md.read_text()

    if "## Build Journal" in content:
        print("Build Journal section already exists in CLAUDE.md")
        return

    # Append to end of file
    with open(claude_md, "a") as f:
        f.write("\n" + CLAUDE_MD_SECTION)

    print("Added Build Journal section to CLAUDE.md")


if __name__ == "__main__":
    main()
