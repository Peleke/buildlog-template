"""Re-export embedding backends from buildlog.embeddings.

Provides clean access to embedding similarity without reaching into
top-level module internals.

Usage:
    from buildlog.engine.embeddings import similarity, TokenBackend
"""

from buildlog.embeddings import (
    EmbeddingBackend,
    OpenAIBackend,
    SentenceTransformerBackend,
    TokenBackend,
    compute_embeddings,
    get_backend,
    similarity,
)

__all__ = [
    "EmbeddingBackend",
    "TokenBackend",
    "SentenceTransformerBackend",
    "OpenAIBackend",
    "get_backend",
    "similarity",
    "compute_embeddings",
]
