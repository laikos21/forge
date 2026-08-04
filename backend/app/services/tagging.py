"""Tags and taggings across every object type."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..domain import TargetType
from ..lib.text import slugify
from ..models import Tag, Tagging
from . import refs


class TagError(ValueError):
    pass


def get_or_create_tag(session: Session, name: str, *, color: str | None = None) -> Tag:
    name = name.strip()
    if not name:
        raise TagError("tag name is empty")
    slug = slugify(name)
    tag = session.execute(select(Tag).where(Tag.slug == slug)).scalar_one_or_none()
    if tag is None:
        tag = Tag(slug=slug, name=name, color=color)
        session.add(tag)
        session.flush()
    elif color and not tag.color:
        tag.color = color
    return tag


def set_tags(session: Session, target_type: str, target_id: str, names: list[str]) -> list[Tag]:
    """Replace the tag set of one object. Returns the resulting tags."""

    TargetType(target_type)
    if not refs.exists(session, target_type, target_id):
        raise TagError(f"{target_type} {target_id} does not exist")

    tags = [get_or_create_tag(session, name) for name in dict.fromkeys(n for n in names if n.strip())]
    wanted = {tag.id for tag in tags}

    current = session.execute(
        select(Tagging).where(Tagging.target_type == target_type, Tagging.target_id == target_id)
    ).scalars().all()
    for tagging in current:
        if tagging.tag_id not in wanted:
            session.delete(tagging)
    existing_ids = {t.tag_id for t in current}
    for tag in tags:
        if tag.id not in existing_ids:
            session.add(Tagging(tag_id=tag.id, target_type=str(target_type), target_id=target_id))
    session.flush()
    return tags


def add_tag(session: Session, target_type: str, target_id: str, name: str) -> Tag:
    tag = get_or_create_tag(session, name)
    existing = session.execute(
        select(Tagging).where(
            Tagging.tag_id == tag.id,
            Tagging.target_type == target_type,
            Tagging.target_id == target_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(Tagging(tag_id=tag.id, target_type=str(target_type), target_id=target_id))
        session.flush()
    return tag


def tags_for(session: Session, target_type: str, target_id: str) -> list[Tag]:
    return list(
        session.execute(
            select(Tag)
            .join(Tagging, Tagging.tag_id == Tag.id)
            .where(Tagging.target_type == target_type, Tagging.target_id == target_id)
            .order_by(Tag.name)
        ).scalars()
    )


def tags_for_many(session: Session, target_type: str, target_ids: list[str]) -> dict[str, list[Tag]]:
    if not target_ids:
        return {}
    rows = session.execute(
        select(Tagging.target_id, Tag)
        .join(Tag, Tagging.tag_id == Tag.id)
        .where(Tagging.target_type == target_type, Tagging.target_id.in_(target_ids))
        .order_by(Tag.name)
    ).all()
    out: dict[str, list[Tag]] = {tid: [] for tid in target_ids}
    for target_id, tag in rows:
        out.setdefault(target_id, []).append(tag)
    return out


def usage_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(Tagging.tag_id, func.count(Tagging.id)).group_by(Tagging.tag_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def targets_with_tags(session: Session, target_type: str, slugs: list[str]) -> set[str]:
    """Ids of ``target_type`` objects carrying *all* of ``slugs``."""

    if not slugs:
        return set()
    rows = session.execute(
        select(Tagging.target_id, func.count(func.distinct(Tag.slug)))
        .join(Tag, Tagging.tag_id == Tag.id)
        .where(Tagging.target_type == target_type, Tag.slug.in_(slugs))
        .group_by(Tagging.target_id)
        .having(func.count(func.distinct(Tag.slug)) == len(set(slugs)))
    ).all()
    return {row[0] for row in rows}


def delete_taggings_for(session: Session, target_type: str, target_id: str) -> int:
    result = session.execute(
        delete(Tagging).where(Tagging.target_type == target_type, Tagging.target_id == target_id)
    )
    return int(result.rowcount or 0)
