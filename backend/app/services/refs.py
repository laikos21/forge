"""Resolution of polymorphic ``(target_type, target_id)`` references.

Tags, links, collection items, dossier items and comparison subjects all point
at "some object". This module is the single place that knows how to turn such a
pair into something displayable, and how to check that it exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..domain import TargetType
from ..lib.text import truncate
from ..models import Collection, Comparison, Dossier, Entity, Excerpt, KnowledgeObject, Source

MODELS: dict[str, type] = {
    TargetType.SOURCE: Source,
    TargetType.EXCERPT: Excerpt,
    TargetType.KNOWLEDGE: KnowledgeObject,
    TargetType.ENTITY: Entity,
    TargetType.DOSSIER: Dossier,
    TargetType.COLLECTION: Collection,
    TargetType.COMPARISON: Comparison,
}


@dataclass(slots=True)
class RefInfo:
    target_type: str
    target_id: str
    exists: bool
    label: str
    sublabel: str = ""
    kind: str = ""
    source_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "exists": self.exists,
            "label": self.label,
            "sublabel": self.sublabel,
            "kind": self.kind,
            "source_id": self.source_id,
        }


def model_for(target_type: str) -> type | None:
    try:
        return MODELS.get(TargetType(target_type))
    except ValueError:
        return None


def fetch(session: Session, target_type: str, target_id: str) -> Any | None:
    model = model_for(target_type)
    if model is None:
        return None
    return session.get(model, target_id)


def exists(session: Session, target_type: str, target_id: str) -> bool:
    return fetch(session, target_type, target_id) is not None


def describe(session: Session, target_type: str, target_id: str) -> RefInfo:
    obj = fetch(session, target_type, target_id)
    if obj is None:
        return RefInfo(target_type, target_id, False, "(deleted or unknown object)")
    if isinstance(obj, Source):
        return RefInfo(target_type, target_id, True, obj.title, obj.kind, obj.kind, obj.id)
    if isinstance(obj, Excerpt):
        source = session.get(Source, obj.source_id)
        return RefInfo(
            target_type,
            target_id,
            True,
            truncate(obj.text, 120),
            f"from {source.title}" if source else "",
            "excerpt",
            obj.source_id,
        )
    if isinstance(obj, KnowledgeObject):
        return RefInfo(target_type, target_id, True, obj.title, f"{obj.kind} · {obj.status}", obj.kind)
    if isinstance(obj, Entity):
        return RefInfo(target_type, target_id, True, obj.name, obj.kind, obj.kind)
    if isinstance(obj, Dossier):
        return RefInfo(target_type, target_id, True, obj.title, obj.subject_kind, obj.subject_kind)
    if isinstance(obj, Collection):
        return RefInfo(target_type, target_id, True, obj.name, "collection", "collection")
    if isinstance(obj, Comparison):
        return RefInfo(target_type, target_id, True, obj.title, "comparison", obj.subject_type)
    return RefInfo(target_type, target_id, True, str(target_id))


def describe_many(session: Session, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], RefInfo]:
    return {pair: describe(session, *pair) for pair in pairs}
