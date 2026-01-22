"""Source management and fetching for the seed engine.

Handles:
- Source manifests (what to fetch)
- Content caching (fetched markdown)
- Incremental fetching (fetch on demand)
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from buildlog.seed_engine.models import Source, SourceType

logger = logging.getLogger(__name__)


class FetchStatus(Enum):
    """Status of a source fetch."""

    PENDING = "pending"  # Not yet fetched
    CACHED = "cached"  # Successfully fetched and cached
    FAILED = "failed"  # Fetch failed
    STALE = "stale"  # Cached but needs refresh


@dataclass
class SourceEntry:
    """A source entry in the manifest with fetch status."""

    source: Source
    status: FetchStatus = FetchStatus.PENDING
    fetched_at: datetime | None = None
    cache_path: str | None = None
    error: str | None = None
    content_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.source.name,
            "url": self.source.url,
            "source_type": self.source.source_type.value,
            "domain": self.source.domain,
            "description": self.source.description,
            "sections": self.source.sections,
            "status": self.status.value,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "cache_path": self.cache_path,
            "error": self.error,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceEntry:
        """Deserialize from dictionary."""
        source = Source(
            name=data["name"],
            url=data["url"],
            source_type=SourceType(data["source_type"]),
            domain=data["domain"],
            description=data.get("description", ""),
            sections=data.get("sections", []),
        )
        fetched_at = None
        if data.get("fetched_at"):
            fetched_at = datetime.fromisoformat(data["fetched_at"])

        return cls(
            source=source,
            status=FetchStatus(data.get("status", "pending")),
            fetched_at=fetched_at,
            cache_path=data.get("cache_path"),
            error=data.get("error"),
            content_hash=data.get("content_hash"),
        )


@dataclass
class SourceManifest:
    """Manifest of sources for a persona.

    Tracks what sources exist, their fetch status, and where
    cached content lives.

    Usage:
        manifest = SourceManifest(persona="test_terrorist")
        manifest.add_source(Source(...))
        manifest.save(Path(".buildlog/sources/test_terrorist"))

        # Later
        manifest = SourceManifest.load(Path(".buildlog/sources/test_terrorist"))
        pending = manifest.get_pending()
    """

    persona: str
    entries: list[SourceEntry] = field(default_factory=list)
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_source(self, source: Source) -> SourceEntry:
        """Add a source to the manifest."""
        # Check for duplicates
        for entry in self.entries:
            if entry.source.url == source.url:
                logger.warning(f"Source already exists: {source.url}")
                return entry

        entry = SourceEntry(source=source)
        self.entries.append(entry)
        self.updated_at = datetime.now(timezone.utc)
        return entry

    def get_by_url(self, url: str) -> SourceEntry | None:
        """Get entry by URL."""
        for entry in self.entries:
            if entry.source.url == url:
                return entry
        return None

    def get_pending(self) -> list[SourceEntry]:
        """Get all entries that haven't been fetched."""
        return [e for e in self.entries if e.status == FetchStatus.PENDING]

    def get_cached(self) -> list[SourceEntry]:
        """Get all entries that have been fetched."""
        return [e for e in self.entries if e.status == FetchStatus.CACHED]

    def get_failed(self) -> list[SourceEntry]:
        """Get all entries that failed to fetch."""
        return [e for e in self.entries if e.status == FetchStatus.FAILED]

    def summary(self) -> dict[str, int]:
        """Get summary of fetch statuses."""
        return {
            "total": len(self.entries),
            "pending": len(self.get_pending()),
            "cached": len(self.get_cached()),
            "failed": len(self.get_failed()),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "persona": self.persona,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceManifest:
        """Deserialize from dictionary."""
        return cls(
            persona=data["persona"],
            version=data.get("version", 1),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            entries=[SourceEntry.from_dict(e) for e in data.get("entries", [])],
        )

    def save(self, base_dir: Path) -> Path:
        """Save manifest to disk.

        Args:
            base_dir: Base directory (e.g., .buildlog/sources/test_terrorist)

        Returns:
            Path to saved manifest file.
        """
        base_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = base_dir / "manifest.yaml"

        with open(manifest_path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

        return manifest_path

    @classmethod
    def load(cls, base_dir: Path) -> SourceManifest | None:
        """Load manifest from disk.

        Args:
            base_dir: Base directory containing manifest.yaml

        Returns:
            Loaded manifest or None if not found.
        """
        manifest_path = base_dir / "manifest.yaml"
        if not manifest_path.exists():
            return None

        with open(manifest_path) as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)


def url_to_cache_filename(url: str) -> str:
    """Convert URL to a safe cache filename.

    Examples:
        https://testing.googleblog.com/2015/04/test.html
        → testing_googleblog_com_2015_04_test.md
    """
    parsed = urlparse(url)

    # Combine host and path
    parts = [parsed.netloc] + [p for p in parsed.path.split("/") if p]

    # Clean each part
    clean_parts = []
    for part in parts:
        # Remove extension
        part = re.sub(r"\.[a-z]+$", "", part)
        # Replace non-alphanumeric with underscore
        part = re.sub(r"[^a-zA-Z0-9]", "_", part)
        # Collapse multiple underscores
        part = re.sub(r"_+", "_", part)
        # Strip leading/trailing underscores
        part = part.strip("_")
        if part:
            clean_parts.append(part)

    # Join and truncate
    filename = "_".join(clean_parts)[:100]
    return f"{filename}.md"


def content_hash(content: str) -> str:
    """Generate hash of content for change detection."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class SourceFetcher:
    """Fetches and caches source content.

    Usage:
        fetcher = SourceFetcher(cache_dir=Path(".buildlog/sources/test_terrorist/cache"))

        # Fetch a single source
        content = fetcher.fetch(entry)

        # Fetch all pending
        results = fetcher.fetch_pending(manifest)
    """

    cache_dir: Path

    def __post_init__(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self, entry: SourceEntry, force: bool = False) -> str | None:
        """Fetch a single source and cache it.

        Args:
            entry: The source entry to fetch.
            force: If True, refetch even if cached.

        Returns:
            Content as markdown, or None if failed.
        """
        # Check cache
        if entry.status == FetchStatus.CACHED and not force:
            if entry.cache_path:
                cache_path = self.cache_dir / entry.cache_path
                if cache_path.exists():
                    return cache_path.read_text()

        # Fetch content
        try:
            content = self._fetch_url(entry.source.url)
            if content is None:
                entry.status = FetchStatus.FAILED
                entry.error = "Failed to fetch content"
                return None

            # Cache it
            filename = url_to_cache_filename(entry.source.url)
            cache_path = self.cache_dir / filename
            cache_path.write_text(content)

            # Update entry
            entry.status = FetchStatus.CACHED
            entry.fetched_at = datetime.now(timezone.utc)
            entry.cache_path = filename
            entry.content_hash = content_hash(content)
            entry.error = None

            logger.info(f"Fetched and cached: {entry.source.name} → {filename}")
            return content

        except Exception as e:
            entry.status = FetchStatus.FAILED
            entry.error = str(e)
            logger.error(f"Failed to fetch {entry.source.url}: {e}")
            return None

    def _fetch_url(self, url: str) -> str | None:
        """Fetch URL and convert to markdown.

        This is a placeholder - in production you'd use:
        - requests + html2text for web pages
        - PDF extractors for PDFs
        - API clients for structured sources

        For now, returns a placeholder indicating manual fetch needed.
        """
        # TODO: Implement actual fetching
        # For now, return a template indicating manual population needed
        return f"""# {url}

> **Note**: This source requires manual population.
>
> Fetch the content from: {url}
> Then paste the relevant sections below.

---

## Content

[Paste content here]

---

## Extracted Rules

[Document rules extracted from this source]
"""

    def fetch_pending(self, manifest: SourceManifest) -> dict[str, bool]:
        """Fetch all pending sources in a manifest.

        Returns:
            Dict mapping URL to success status.
        """
        results = {}
        for entry in manifest.get_pending():
            content = self.fetch(entry)
            results[entry.source.url] = content is not None
        return results

    def get_cached_content(self, entry: SourceEntry) -> str | None:
        """Get cached content for an entry."""
        if entry.cache_path:
            cache_path = self.cache_dir / entry.cache_path
            if cache_path.exists():
                return cache_path.read_text()
        return None
