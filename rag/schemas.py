"""Shared dataclasses for the RAG layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Chunk:
    """A single retrievable chunk — one slice of a playbook."""

    id: str
    playbook_slug: str
    section: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float  # cosine similarity in [-1, 1]; higher is more similar
