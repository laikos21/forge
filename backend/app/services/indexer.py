"""Maintenance of the SQLite FTS5 index.

The index is written by the application rather than by SQL triggers. Triggers
would only see raw column values, while what FORGE wants to index is a
*composed* document (a knowledge object's title + body + kind, a dossier's
overview + bull + bear + risks). Keeping composition in Python makes it
explicit, testable and rebuildable.
"""

from __future__ import annotations

from sqlalchemy import text as sql
from sqlalchemy.orm import Session

from ..domain import TargetType
from ..models import Dossier, Entity, Excerpt, KnowledgeObject, Source

TABLE = "search_index"

_DELETE = sql(f"DELETE FROM {TABLE} WHERE ref_type = :ref_type AND ref_id = :ref_id")
_INSERT = sql(
    f"INSERT INTO {TABLE} (ref_type, ref_id, source_id, kind, title, body) "
    "VALUES (:ref_type, :ref_id, :source_id, :kind, :title, :body)"
)


def remove(session: Session, ref_type: str, ref_id: str) -> None:
    session.execute(_DELETE, {"ref_type": str(ref_type), "ref_id": ref_id})


def _write(
    session: Session,
    ref_type: str,
    ref_id: str,
    *,
    title: str,
    body: str,
    kind: str,
    source_id: str | None = None,
) -> None:
    remove(session, ref_type, ref_id)
    session.execute(
        _INSERT,
        {
            "ref_type": str(ref_type),
            "ref_id": ref_id,
            "source_id": source_id,
            "kind": kind,
            "title": title or "",
            "body": body or "",
        },
    )


def index_source(session: Session, source: Source) -> None:
    detected = source.detected_metadata or {}
    extras = [
        source.author or "",
        source.publisher or "",
        source.source_url or "",
        source.summary or "",
        " ".join(str(t) for t in detected.get("tickers_detected", [])),
        " ".join(str(c) for c in detected.get("companies_detected", [])),
    ]
    _write(
        session,
        TargetType.SOURCE,
        source.id,
        title=source.title,
        body="\n".join([source.text, *[e for e in extras if e]]),
        kind=source.kind,
        source_id=source.id,
    )


def index_excerpt(session: Session, excerpt: Excerpt) -> None:
    _write(
        session,
        TargetType.EXCERPT,
        excerpt.id,
        title=(excerpt.note or excerpt.text)[:200],
        body="\n".join(filter(None, [excerpt.text, excerpt.note])),
        kind="excerpt",
        source_id=excerpt.source_id,
    )


def index_knowledge(session: Session, obj: KnowledgeObject) -> None:
    _write(
        session,
        TargetType.KNOWLEDGE,
        obj.id,
        title=obj.title,
        body="\n".join(filter(None, [obj.body, obj.outcome, obj.kind, obj.status])),
        kind=obj.kind,
    )


def index_dossier(session: Session, dossier: Dossier) -> None:
    _write(
        session,
        TargetType.DOSSIER,
        dossier.id,
        title=dossier.title,
        body="\n".join(
            filter(
                None,
                [
                    dossier.overview,
                    dossier.thesis,
                    dossier.bull_case,
                    dossier.bear_case,
                    dossier.risks,
                    dossier.open_questions,
                ],
            )
        ),
        kind=dossier.subject_kind,
    )


def index_entity(session: Session, entity: Entity) -> None:
    aliases = " ".join(entity.aliases or [])
    _write(
        session,
        TargetType.ENTITY,
        entity.id,
        title=entity.name,
        body="\n".join(filter(None, [entity.description or "", aliases, entity.kind])),
        kind=entity.kind,
    )


INDEXERS = {
    TargetType.SOURCE: (Source, index_source),
    TargetType.EXCERPT: (Excerpt, index_excerpt),
    TargetType.KNOWLEDGE: (KnowledgeObject, index_knowledge),
    TargetType.DOSSIER: (Dossier, index_dossier),
    TargetType.ENTITY: (Entity, index_entity),
}


def reindex_object(session: Session, ref_type: str, ref_id: str) -> bool:
    entry = INDEXERS.get(TargetType(ref_type))
    if entry is None:
        return False
    model, indexer = entry
    obj = session.get(model, ref_id)
    if obj is None:
        remove(session, ref_type, ref_id)
        return False
    indexer(session, obj)
    return True


def rebuild_all(session: Session) -> dict[str, int]:
    """Drop and repopulate the whole index. Safe to run at any time."""

    session.execute(sql(f"DELETE FROM {TABLE}"))
    counts: dict[str, int] = {}
    for ref_type, (model, indexer) in INDEXERS.items():
        rows = session.query(model).all()
        for row in rows:
            indexer(session, row)
        counts[str(ref_type)] = len(rows)
    session.flush()
    return counts


def index_count(session: Session) -> int:
    return int(session.execute(sql(f"SELECT count(*) FROM {TABLE}")).scalar_one())
