"""Optional local semantic search, behind a narrow adapter.

The contract is deliberately thin - build an index, query it - so the rest of
FORGE never learns whether embeddings exist. With the feature off (the default)
:func:`status` reports why, :func:`query` returns nothing, and full-text search
is unaffected.

Vectors are stored as little-endian float32 blobs and compared in Python. For a
single-user corpus of thousands of documents that is fast enough and avoids a
native vector-index dependency.
"""

from __future__ import annotations

import array
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..domain import TargetType
from ..models import Embedding, Excerpt, Source
from . import settings_store
from .llm import LLMUnavailable, provider_for

MAX_CHARS_PER_VECTOR = 4000


@dataclass(slots=True)
class SemanticStatus:
    enabled: bool
    available: bool
    detail: str
    model: str
    indexed: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "available": self.available,
            "detail": self.detail,
            "model": self.model,
            "indexed": self.indexed,
        }


def _pack(vector: list[float]) -> tuple[bytes, float]:
    packed = array.array("f", vector)
    if packed.itemsize != 4:  # pragma: no cover - platform sanity check
        raise RuntimeError("float32 array is not 4 bytes wide on this platform")
    import sys

    if sys.byteorder != "little":  # pragma: no cover
        packed.byteswap()
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return packed.tobytes(), norm


def _unpack(blob: bytes) -> list[float]:
    packed = array.array("f")
    packed.frombytes(blob)
    import sys

    if sys.byteorder != "little":  # pragma: no cover
        packed.byteswap()
    return list(packed)


def status(session: Session) -> SemanticStatus:
    preferences = settings_store.get_all(session)
    model = preferences["semantic.model"]
    indexed = len(session.execute(select(Embedding.id).where(Embedding.model == model)).all())
    if not preferences["semantic.enabled"]:
        return SemanticStatus(False, False, "Semantic search is disabled in Settings.", model, indexed)
    provider = provider_for(session, force=True)
    if provider is None:
        return SemanticStatus(True, False, "No local embedding provider is configured.", model, indexed)
    provider_state = provider.status()
    if not provider_state.available:
        return SemanticStatus(True, False, provider_state.detail, model, indexed)
    return SemanticStatus(
        True,
        True,
        f"Ready. {indexed} objects indexed with '{model}'.",
        model,
        indexed,
    )


def build_index(session: Session, *, limit: int | None = None) -> dict[str, Any]:
    preferences = settings_store.get_all(session)
    if not preferences["semantic.enabled"]:
        return {"indexed": 0, "skipped": 0, "detail": "Semantic search is disabled in Settings."}
    provider = provider_for(session)
    if provider is None:
        return {"indexed": 0, "skipped": 0, "detail": "Local LLM features are disabled in Settings."}

    model = preferences["semantic.model"]
    existing = {
        (row.ref_type, row.ref_id)
        for row in session.execute(
            select(Embedding.ref_type, Embedding.ref_id).where(Embedding.model == model)
        ).all()
    }

    targets: list[tuple[str, str, str | None, str]] = []
    for source in session.execute(select(Source)).scalars():
        if (TargetType.SOURCE, source.id) not in existing and source.text.strip():
            targets.append((TargetType.SOURCE, source.id, source.id, f"{source.title}\n\n{source.text}"))
    for excerpt in session.execute(select(Excerpt)).scalars():
        if (TargetType.EXCERPT, excerpt.id) not in existing:
            targets.append((TargetType.EXCERPT, excerpt.id, excerpt.source_id, excerpt.text))

    if limit:
        targets = targets[:limit]
    if not targets:
        return {"indexed": 0, "skipped": len(existing), "detail": "Index is already up to date."}

    try:
        vectors = provider.embed([text[:MAX_CHARS_PER_VECTOR] for *_, text in targets], model=model)
    except LLMUnavailable as exc:
        return {"indexed": 0, "skipped": 0, "detail": str(exc), "error": True}

    for (ref_type, ref_id, source_id, _), vector in zip(targets, vectors, strict=True):
        blob, norm = _pack(vector)
        session.add(
            Embedding(
                ref_type=str(ref_type),
                ref_id=ref_id,
                source_id=source_id,
                model=model,
                dim=len(vector),
                vector=blob,
                norm=Decimal(repr(norm)),
            )
        )
    session.flush()
    return {"indexed": len(targets), "skipped": len(existing), "detail": f"Indexed {len(targets)} objects."}


def clear_index(session: Session) -> int:
    result = session.execute(delete(Embedding))
    return int(result.rowcount or 0)


def query(session: Session, text: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Cosine-similarity search. Returns ``[]`` whenever the feature is off."""

    state = status(session)
    if not state.enabled or not state.available:
        return []
    provider = provider_for(session)
    if provider is None:
        return []
    try:
        vector = provider.embed([text[:MAX_CHARS_PER_VECTOR]], model=state.model)[0]
    except LLMUnavailable:
        return []

    query_norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    rows = session.execute(select(Embedding).where(Embedding.model == state.model)).scalars().all()
    scored: list[dict[str, Any]] = []
    for row in rows:
        candidate = _unpack(row.vector)
        if len(candidate) != len(vector):
            continue
        dot = sum(a * b for a, b in zip(vector, candidate, strict=True))
        candidate_norm = math.sqrt(sum(v * v for v in candidate)) or 1.0
        scored.append(
            {
                "ref_type": row.ref_type,
                "ref_id": row.ref_id,
                "source_id": row.source_id,
                "similarity": round(dot / (query_norm * candidate_norm), 6),
            }
        )
    scored.sort(key=lambda item: -item["similarity"])
    return scored[:limit]
