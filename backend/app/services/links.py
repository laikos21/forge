"""Bidirectional relationships.

An edge is stored once, in the direction the user created it. Reads always look
at both ends: querying the neighbours of X returns outgoing edges as-is and
incoming edges relabelled with their inverse relation, so a link created from a
source to a dossier is visible from the dossier as ``contains`` without a second
row that could drift out of sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..domain import RELATION_INVERSES, TargetType, inverse_relation
from ..models import Link
from . import refs


class LinkError(ValueError):
    pass


@dataclass(slots=True)
class Neighbour:
    link_id: str
    relation: str
    direction: str  # outgoing | incoming
    note: str | None
    origin: str
    ref: refs.RefInfo

    def as_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "relation": self.relation,
            "direction": self.direction,
            "note": self.note,
            "origin": self.origin,
            **self.ref.as_dict(),
        }


def validate(session: Session, from_type: str, from_id: str, to_type: str, to_id: str, relation: str) -> None:
    if relation not in RELATION_INVERSES:
        raise LinkError(f"unknown relation {relation!r}")
    if (from_type, from_id) == (to_type, to_id):
        raise LinkError("an object cannot be linked to itself")
    for target_type, target_id in ((from_type, from_id), (to_type, to_id)):
        TargetType(target_type)
        if not refs.exists(session, target_type, target_id):
            raise LinkError(f"{target_type} {target_id} does not exist")


def create_link(
    session: Session,
    *,
    from_type: str,
    from_id: str,
    to_type: str,
    to_id: str,
    relation: str = "related_to",
    note: str | None = None,
    origin: str = "user",
) -> Link:
    validate(session, from_type, from_id, to_type, to_id, relation)
    existing = session.execute(
        select(Link).where(
            Link.from_type == from_type,
            Link.from_id == from_id,
            Link.to_type == to_type,
            Link.to_id == to_id,
            Link.relation == relation,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if note and not existing.note:
            existing.note = note
        return existing

    # A symmetric relation stored in the other direction is the same edge.
    mirrored = session.execute(
        select(Link).where(
            Link.from_type == to_type,
            Link.from_id == to_id,
            Link.to_type == from_type,
            Link.to_id == from_id,
            Link.relation == inverse_relation(relation),
        )
    ).scalar_one_or_none()
    if mirrored is not None:
        return mirrored

    link = Link(
        from_type=str(from_type),
        from_id=from_id,
        to_type=str(to_type),
        to_id=to_id,
        relation=relation,
        note=note,
        origin=origin,
    )
    session.add(link)
    session.flush()
    return link


def neighbours(session: Session, target_type: str, target_id: str) -> list[Neighbour]:
    rows = session.execute(
        select(Link).where(
            or_(
                (Link.from_type == target_type) & (Link.from_id == target_id),
                (Link.to_type == target_type) & (Link.to_id == target_id),
            )
        )
    ).scalars().all()

    out: list[Neighbour] = []
    for link in rows:
        outgoing = link.from_type == target_type and link.from_id == target_id
        other_type, other_id = (link.to_type, link.to_id) if outgoing else (link.from_type, link.from_id)
        out.append(
            Neighbour(
                link_id=link.id,
                relation=link.relation if outgoing else inverse_relation(link.relation),
                direction="outgoing" if outgoing else "incoming",
                note=link.note,
                origin=link.origin,
                ref=refs.describe(session, other_type, other_id),
            )
        )
    out.sort(key=lambda n: (n.relation, n.ref.label.lower()))
    return out


def delete_link(session: Session, link_id: str) -> bool:
    link = session.get(Link, link_id)
    if link is None:
        return False
    session.delete(link)
    return True


def delete_links_for(session: Session, target_type: str, target_id: str) -> int:
    rows = session.execute(
        select(Link).where(
            or_(
                (Link.from_type == target_type) & (Link.from_id == target_id),
                (Link.to_type == target_type) & (Link.to_id == target_id),
            )
        )
    ).scalars().all()
    for link in rows:
        session.delete(link)
    return len(rows)
