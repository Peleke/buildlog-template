"""MkDocs hook: generate llms-full.txt from llms.txt + source markdown.

Runs on_pre_build so the generated file is available for MkDocs to copy
to the site output directory.

The hook parses docs/llms.txt, extracts markdown links, resolves them to
local source files in docs/, and concatenates everything into docs/llms-full.txt.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

SITE_URL = "https://peleke.github.io/buildlog-template/"
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
LLMS_TXT = DOCS_DIR / "llms.txt"
LLMS_FULL_TXT = DOCS_DIR / "llms-full.txt"


def _url_to_local_path(url: str) -> Path | None:
    """Convert a site URL to a local docs/ markdown file path."""
    parsed = urlparse(url)
    path = parsed.path

    # Strip the site prefix
    prefix = "/buildlog-template/"
    if not path.startswith(prefix):
        return None
    relative = path[len(prefix) :]

    # Trailing slash -> index.md inside that directory
    if relative.endswith("/"):
        relative += "index.md"
    elif not relative.endswith(".md"):
        relative += ".md"

    # MkDocs URL convention: getting-started/installation/ -> getting-started/installation.md
    # But also could be getting-started/installation/index.md — try both
    candidate = DOCS_DIR / relative
    if candidate.exists():
        return candidate

    # Try without the trailing directory (installation/ -> installation.md)
    if relative.endswith("/index.md"):
        alt = DOCS_DIR / relative.replace("/index.md", ".md")
        if alt.exists():
            return alt

    return None


def _parse_llms_txt(content: str) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Parse llms.txt into preamble lines and (section, name, url) entries.

    Returns:
        preamble: Lines before the first link entry (H1, blockquote, paragraphs).
        entries: List of (section_heading, link_name, url) tuples.
    """
    preamble: list[str] = []
    entries: list[tuple[str, str, str]] = []
    current_section = ""
    in_preamble = True

    for line in content.splitlines():
        # Track H2 sections
        h2_match = re.match(r"^## (.+)$", line)
        if h2_match:
            current_section = h2_match.group(1)
            in_preamble = False
            continue

        # Match link entries: - [Name](URL): Description
        link_match = re.match(r"^- \[(.+?)\]\((.+?)\)", line)
        if link_match:
            name = link_match.group(1)
            url = link_match.group(2)
            entries.append((current_section, name, url))
            in_preamble = False
            continue

        if in_preamble:
            preamble.append(line)

    return preamble, entries


def generate_llms_full() -> str:
    """Generate llms-full.txt content from llms.txt + source markdown."""
    llms_content = LLMS_TXT.read_text()
    preamble, entries = _parse_llms_txt(llms_content)

    parts: list[str] = []

    # Include preamble (H1, blockquote, overview paragraphs)
    parts.append("\n".join(preamble).strip())
    parts.append("")

    current_section = ""
    for section, name, url in entries:
        # Emit section header on change
        if section != current_section:
            current_section = section
            parts.append(f"\n## {section}\n")

        local_path = _url_to_local_path(url)
        if local_path and local_path.exists():
            md_content = local_path.read_text().strip()
            parts.append(md_content)
            parts.append("")  # blank line between entries
        else:
            # Fallback: keep the link reference
            parts.append(f"### {name}\n\nSee: {url}\n")

    return "\n".join(parts)


# --- MkDocs hook entry point ---


def on_pre_build(**kwargs) -> None:  # noqa: ARG001
    """Generate llms-full.txt before MkDocs builds the site."""
    if not LLMS_TXT.exists():
        return
    content = generate_llms_full()
    LLMS_FULL_TXT.write_text(content)


# --- CLI entry point for manual generation ---

if __name__ == "__main__":
    if not LLMS_TXT.exists():
        print(f"Error: {LLMS_TXT} not found")
        raise SystemExit(1)
    content = generate_llms_full()
    LLMS_FULL_TXT.write_text(content)
    print(f"Generated {LLMS_FULL_TXT} ({len(content)} bytes)")
