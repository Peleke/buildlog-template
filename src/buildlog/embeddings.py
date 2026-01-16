"""Embedding backends for semantic similarity.

This module provides a pluggable interface for computing text embeddings.
The default is token-based (no dependencies). Optional backends include:

- sentence-transformers (local, offline): pip install buildlog[embeddings]
- OpenAI API: requires OPENAI_API_KEY
- Anthropic API: requires ANTHROPIC_API_KEY (future)

Usage:
    from buildlog.embeddings import get_backend, similarity

    # Default (token-based)
    sim = similarity("run type checker", "tsc before commit")

    # With embeddings
    backend = get_backend("sentence-transformers")
    sim = similarity("run type checker", "tsc before commit", backend=backend)
"""

from __future__ import annotations

__all__ = [
    "EmbeddingBackend",
    "TokenBackend",
    "SentenceTransformerBackend",
    "OpenAIBackend",
    "get_backend",
    "similarity",
    "compute_embeddings",
]

import logging
import os
import re
import threading
from abc import ABC, abstractmethod
from typing import Final, Literal

import numpy as np

logger = logging.getLogger(__name__)

# Type alias for embedding vectors
Embedding = list[float]
BackendName = Literal["token", "sentence-transformers", "openai"]

# Stop words to filter in token-based approach
STOP_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "dare",
        "ought",
        "used",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "also",
        "now",
        "always",
        "never",
        "often",
        "still",
        "already",
        "ever",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "what",
        "which",
        "who",
        "whom",
        "whose",
    }
)

# Common synonyms for normalization
SYNONYMS: Final[dict[str, str]] = {
    # Type checking
    "tsc": "typescript",
    "mypy": "typecheck",
    "pyright": "typecheck",
    "typechecker": "typecheck",
    "type-checker": "typecheck",
    "type_checker": "typecheck",
    # Version control
    "commit": "commit",
    "committing": "commit",
    "commits": "commit",
    "committed": "commit",
    "git": "git",
    "github": "git",
    # Testing
    "test": "test",
    "tests": "test",
    "testing": "test",
    "tested": "test",
    "unittest": "test",
    "pytest": "test",
    # Running
    "run": "run",
    "running": "run",
    "runs": "run",
    "execute": "run",
    "executing": "run",
    # Checking
    "check": "check",
    "checker": "check",
    "checking": "check",
    "checks": "check",
    "verify": "check",
    "verifying": "check",
    "validate": "check",
    "validating": "check",
    # Type checking
    "type": "type",
    "types": "type",
    "typed": "type",
    "typing": "type",
}


class EmbeddingBackend(ABC):
    """Abstract base class for embedding backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this backend."""
        ...

    @abstractmethod
    def embed(self, texts: list[str]) -> list[Embedding]:
        """Compute embeddings for a list of texts.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (same length as input).
        """
        ...

    def similarity(self, a: str, b: str) -> float:
        """Compute similarity between two texts.

        Default implementation uses cosine similarity of embeddings.
        Subclasses may override for efficiency.
        """
        embeddings = self.embed([a, b])
        return _cosine_similarity(embeddings[0], embeddings[1])


def _cosine_similarity(a: Embedding, b: Embedding) -> float:
    """Compute cosine similarity between two vectors."""
    a_arr = np.array(a)
    b_arr = np.array(b)

    dot = np.dot(a_arr, b_arr)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot / (norm_a * norm_b))


class TokenBackend(EmbeddingBackend):
    """Token-based similarity using Jaccard index with normalization.

    This is the default backend with zero external dependencies.
    It normalizes text, applies synonyms, and computes Jaccard similarity.
    """

    @property
    def name(self) -> str:
        return "token"

    def _tokenize(self, text: str) -> set[str]:
        """Tokenize and normalize text."""
        # Lowercase and split on non-alphanumeric
        tokens = re.split(r"[^a-z0-9]+", text.lower())

        # Filter empty and stop words, apply synonyms
        normalized = set()
        for token in tokens:
            if not token or token in STOP_WORDS:
                continue
            # Apply synonym normalization
            normalized_token = SYNONYMS.get(token, token)
            normalized.add(normalized_token)

        return normalized

    def embed(self, texts: list[str]) -> list[Embedding]:
        """Token backend doesn't produce real embeddings.

        Returns a sparse vector representation for compatibility.
        """
        # Build vocabulary from all texts
        vocab: dict[str, int] = {}
        tokenized = [self._tokenize(t) for t in texts]

        for tokens in tokenized:
            for token in tokens:
                if token not in vocab:
                    vocab[token] = len(vocab)

        # Create sparse vectors
        embeddings: list[Embedding] = []
        for tokens in tokenized:
            vec = [0.0] * len(vocab)
            for token in tokens:
                if token in vocab:
                    vec[vocab[token]] = 1.0
            embeddings.append(vec)

        return embeddings

    def similarity(self, a: str, b: str) -> float:
        """Compute Jaccard similarity between tokenized texts."""
        tokens_a = self._tokenize(a)
        tokens_b = self._tokenize(b)

        if not tokens_a or not tokens_b:
            return 0.0

        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)

        return intersection / union if union > 0 else 0.0


class SentenceTransformerBackend(EmbeddingBackend):
    """Local embedding backend using sentence-transformers.

    Requires: pip install buildlog[embeddings]
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize with a specific model.

        Args:
            model_name: HuggingFace model name. Default is a small, fast model.
        """
        self._model_name = model_name
        self._model = None

    @property
    def name(self) -> str:
        return f"sentence-transformers ({self._model_name})"

    def _get_model(self):
        """Lazy-load the model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers is required for local embeddings. "
                    "Install with: pip install buildlog[embeddings]"
                ) from e

            self._model = SentenceTransformer(self._model_name)  # type: ignore[assignment]

        return self._model

    def embed(self, texts: list[str]) -> list[Embedding]:
        """Compute embeddings using sentence-transformers."""
        model = self._get_model()
        embeddings = model.encode(texts, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings]


class OpenAIBackend(EmbeddingBackend):
    """Embedding backend using OpenAI API.

    Requires: OPENAI_API_KEY environment variable.
    """

    def __init__(self, model: str = "text-embedding-3-small"):
        """Initialize with a specific model.

        Args:
            model: OpenAI embedding model name.

        Raises:
            ValueError: If OPENAI_API_KEY is not set.
        """
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError(
                "OpenAI backend requires OPENAI_API_KEY environment variable. "
                "Set it with: export OPENAI_API_KEY=your-key"
            )
        self._model = model
        self._client = None

    @property
    def name(self) -> str:
        return f"openai ({self._model})"

    def _get_client(self):
        """Lazy-load the OpenAI client."""
        if self._client is None:
            try:
                import openai
            except ImportError as e:
                raise ImportError(
                    "openai package is required for OpenAI embeddings. "
                    "Install with: pip install openai"
                ) from e

            self._client = openai.OpenAI()  # type: ignore[assignment]

        return self._client

    def embed(self, texts: list[str]) -> list[Embedding]:
        """Compute embeddings using OpenAI API."""
        client = self._get_client()
        response = client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in response.data]


# Backend registry
_BACKENDS: dict[BackendName, type[EmbeddingBackend]] = {
    "token": TokenBackend,
    "sentence-transformers": SentenceTransformerBackend,
    "openai": OpenAIBackend,
}

# Default backend instance (singleton) with thread safety
_default_backend: EmbeddingBackend | None = None
_default_backend_lock = threading.Lock()


def get_backend(name: BackendName = "token", **kwargs) -> EmbeddingBackend:
    """Get an embedding backend by name.

    Args:
        name: Backend name - "token", "sentence-transformers", or "openai".
        **kwargs: Additional arguments passed to backend constructor.

    Returns:
        EmbeddingBackend instance.

    Raises:
        ValueError: If backend name is not recognized.
    """
    backend_class = _BACKENDS.get(name)
    if backend_class is None:
        raise ValueError(
            f"Unknown embedding backend: {name}. "
            f"Available: {list(_BACKENDS.keys())}"
        )

    return backend_class(**kwargs)


def get_default_backend() -> EmbeddingBackend:
    """Get the default backend (token-based).

    Thread-safe singleton pattern.
    """
    global _default_backend
    if _default_backend is None:
        with _default_backend_lock:
            # Double-check after acquiring lock
            if _default_backend is None:
                _default_backend = TokenBackend()
    return _default_backend


def similarity(a: str, b: str, backend: EmbeddingBackend | None = None) -> float:
    """Compute similarity between two texts.

    Args:
        a: First text.
        b: Second text.
        backend: Embedding backend to use. Defaults to token-based.

    Returns:
        Similarity score between 0 and 1.
    """
    if backend is None:
        backend = get_default_backend()
    return backend.similarity(a, b)


def compute_embeddings(
    texts: list[str],
    backend: EmbeddingBackend | None = None,
) -> list[Embedding]:
    """Compute embeddings for a list of texts.

    Args:
        texts: List of strings to embed.
        backend: Embedding backend to use. Defaults to token-based.

    Returns:
        List of embedding vectors.
    """
    if backend is None:
        backend = get_default_backend()
    return backend.embed(texts)
