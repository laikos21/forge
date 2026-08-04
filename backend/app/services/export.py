"""Markdown and JSON export.

Exports are plain, portable Markdown: every derived statement carries its
citation inline, so an exported dossier stays useful in Obsidian, a git repo or
a plain text editor with no FORGE around it.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import zipfile
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import __version__
from ..domain import TargetType
from ..lib.provenance import locator_label
from ..lib.text import slugify
from ..models import (
    Comparison,
    Dossier,
    Entity,
    EntityMention,
    Excerpt,
    KnowledgeObject,
    Source,
)
from . import dossiers as dossier_service
from . import links, storage, tagging

GENERATED_BANNER = (
    "> ⚙ Contains model-generated text. Generated passages are marked "
    "`[generated]` and were reviewed by the user before export."
)


def _fence(text: str) -> str:
    return text.strip() or "_(empty)_"


def _front_matter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(json.dumps(str(v)) for v in value)}]")
        else:
            lines.append(f"{key}: {json.dumps(str(value))}")
    lines.append("---")
    return "\n".join(lines)


def source_citation(source: Source, locator: dict[str, Any] | None = None) -> str:
    bits = [source.title]
    if source.author:
        bits.append(source.author)
    if source.published_on:
        bits.append(source.published_on.isoformat())
    label = locator_label(locator)
    if label:
        bits.append(label)
    text = " — ".join(bits)
    return f"{text} <{source.source_url}>" if source.source_url else text


def render_source(session: Session, source: Source, *, include_text: bool = True) -> str:
    tags = [t.name for t in tagging.tags_for(session, TargetType.SOURCE, source.id)]
    entities = session.execute(
        select(Entity).join(EntityMention, EntityMention.entity_id == Entity.id).where(
            EntityMention.source_id == source.id
        )
    ).scalars().all()

    out = [
        _front_matter(
            {
                "title": source.title,
                "kind": source.kind,
                "author": source.author,
                "published_on": source.published_on.isoformat() if source.published_on else None,
                "url": source.source_url,
                "imported_at": source.imported_at.isoformat(),
                "content_sha256": source.content_hash,
                "extraction_method": source.extraction_method,
                "tags": tags,
                "forge_id": source.id,
                "demo_content": "yes" if source.is_demo else None,
            }
        ),
        "",
        f"# {source.title}",
        "",
    ]
    if source.is_demo:
        out += ["> **Demonstration content** shipped with FORGE as a worked example.", ""]
    if source.summary:
        out += ["## Summary (deterministic extract)", "", _fence(source.summary), ""]
    if entities:
        out += [
            "## Entities",
            "",
            *[f"- **{e.kind}** — {e.name}" for e in entities],
            "",
        ]
    excerpts = session.execute(
        select(Excerpt).where(Excerpt.source_id == source.id).order_by(Excerpt.char_start)
    ).scalars().all()
    if excerpts:
        out += ["## Excerpts", ""]
        for excerpt in excerpts:
            out += [
                f"> {excerpt.text.strip()}",
                "",
                f"— {source_citation(source, excerpt.locator)}",
                "",
            ]
            if excerpt.note:
                out += [f"*Note:* {excerpt.note}", ""]
    if source.extraction_warnings:
        out += ["## Extraction warnings", "", *[f"- {w}" for w in source.extraction_warnings], ""]
    if include_text and source.text:
        out += ["## Extracted text", "", "```text", source.text, "```", ""]
    return "\n".join(out).rstrip() + "\n"


def render_knowledge(session: Session, obj: KnowledgeObject) -> str:
    tags = [t.name for t in tagging.tags_for(session, TargetType.KNOWLEDGE, obj.id)]
    out = [
        _front_matter(
            {
                "title": obj.title,
                "kind": obj.kind,
                "status": obj.status,
                "confidence": obj.confidence,
                "origin": obj.origin,
                "generated_by": obj.generated_by,
                "review_due_on": obj.review_due_on.isoformat() if obj.review_due_on else None,
                "created_at": obj.created_at.isoformat(),
                "tags": tags,
                "forge_id": obj.id,
            }
        ),
        "",
        f"# {obj.title}",
        "",
        f"`{obj.kind}` · status **{obj.status}**"
        + (f" · confidence {obj.confidence}%" if obj.confidence is not None else ""),
        "",
    ]
    if obj.origin == "generated":
        out += [f"> ⚙ **[generated]** drafted with {obj.generated_by or 'a local model'} and kept editable.", ""]
    out += [_fence(obj.body), ""]
    if obj.outcome:
        out += ["## Outcome", "", _fence(obj.outcome), ""]
    if obj.excerpt_links:
        out += ["## Evidence", ""]
        for link in obj.excerpt_links:
            excerpt = link.excerpt
            source = session.get(Source, excerpt.source_id)
            out += [
                f"**{link.stance}**",
                "",
                f"> {excerpt.text.strip()}",
                "",
                f"— {source_citation(source, excerpt.locator) if source else '(source deleted)'}",
                "",
            ]
            if link.note:
                out += [f"*{link.note}*", ""]
    return "\n".join(out).rstrip() + "\n"


def render_dossier(session: Session, dossier: Dossier) -> str:
    data = dossier_service.detail(session, dossier)
    tags = [t["name"] for t in data["tags"]]
    has_generated = any(c["origin"] == "generated" for c in data["claims"])

    out = [
        _front_matter(
            {
                "title": dossier.title,
                "subject": dossier.subject_kind,
                "status": dossier.status,
                "slug": dossier.slug,
                "updated_at": dossier.updated_at.isoformat(),
                "tags": tags,
                "forge_id": dossier.id,
                "demo_content": "yes" if dossier.is_demo else None,
            }
        ),
        "",
        f"# {dossier.title}",
        "",
        f"*{dossier.subject_kind} dossier · status {dossier.status} · "
        f"exported {dt.datetime.now(dt.UTC).date().isoformat()} by FORGE {__version__}*",
        "",
    ]
    if dossier.is_demo:
        out += ["> **Demonstration content** shipped with FORGE as a worked example.", ""]
    if has_generated:
        out += [GENERATED_BANNER, ""]

    out += ["## Overview", "", _fence(dossier.overview), ""]
    if dossier.thesis.strip():
        out += ["## Thesis", "", _fence(dossier.thesis), ""]

    stance_titles = {
        "bull": "Bull case claims",
        "bear": "Bear case claims",
        "risk": "Risks",
        "question": "Open questions",
        "neutral": "Other claims",
    }
    out += ["## Bull case", "", _fence(dossier.bull_case), ""]
    out += ["## Bear case", "", _fence(dossier.bear_case), ""]
    out += ["## Risks", "", _fence(dossier.risks), ""]
    out += ["## Open questions", "", _fence(dossier.open_questions), ""]

    if data["claims"]:
        out += ["## Claims and evidence", ""]
        for stance in ("bull", "bear", "risk", "question", "neutral"):
            claims = [c for c in data["claims"] if c["stance"] == stance]
            if not claims:
                continue
            out += [f"### {stance_titles[stance]}", ""]
            for claim in claims:
                marker = " `[generated]`" if claim["origin"] == "generated" else ""
                confidence = f" _(confidence {claim['confidence']}%)_" if claim["confidence"] is not None else ""
                out += [f"- **{claim['text']}**{marker}{confidence}"]
                for evidence in claim["evidence"]:
                    if evidence.get("text"):
                        out += [
                            f"    - {evidence['stance']}: “{evidence['text'].strip()}”",
                            f"      — {evidence.get('source_title', 'unknown source')}"
                            + (f" {locator_label(evidence.get('locator'))}" if evidence.get("locator") else ""),
                        ]
                    else:
                        out += [f"    - {evidence['stance']}: {evidence.get('source_title', 'source')}"]
                    if evidence.get("note"):
                        out += [f"      *{evidence['note']}*"]
            out += [""]

    if data["timeline"]:
        out += ["## Timeline", ""]
        for event in data["timeline"]:
            line = f"- **{event['occurred_on']}** — {event['title']}"
            if event.get("source_title"):
                line += f" _(source: {event['source_title']})_"
            out += [line]
            if event.get("description"):
                out += [f"    {event['description']}"]
        out += [""]

    by_section: dict[str, list[dict[str, Any]]] = {}
    for item in data["items"]:
        by_section.setdefault(item["section"], []).append(item)
    section_titles = {
        "sources": "Linked sources",
        "evidence": "Linked excerpts",
        "knowledge": "Knowledge objects",
        "entities": "Linked entities",
        "notes": "Notes",
        "watchlist": "Watchlist",
    }
    for section, items in by_section.items():
        out += [f"## {section_titles.get(section, section.title())}", ""]
        for item in items:
            line = f"- {item['label']}"
            if item["sublabel"]:
                line += f" — _{item['sublabel']}_"
            if item["note"]:
                line += f" — {item['note']}"
            out += [line]
        out += [""]

    if data["related_entities"]:
        out += ["## Related entities", ""]
        for entity in data["related_entities"]:
            out += [f"- **{entity['kind']}** {entity['name']} _(via {entity['via']})_"]
        out += [""]

    if data["links"]:
        out += ["## Relationships", ""]
        for link in data["links"]:
            out += [f"- {link['relation']} → {link['label']} ({link['target_type']})"]
        out += [""]

    if tags:
        out += ["## Tags", "", ", ".join(f"`{t}`" for t in tags), ""]

    return "\n".join(out).rstrip() + "\n"


def render_comparison(session: Session, comparison: Comparison) -> str:
    subjects = sorted(comparison.subjects, key=lambda s: s.position)
    dimensions = sorted(comparison.dimensions, key=lambda d: d.position)
    cells = {(c.subject_id, c.dimension_id): c for c in comparison.cells}

    header = "| Dimension | " + " | ".join(s.label or s.target_id for s in subjects) + " |"
    divider = "| --- " * (len(subjects) + 1) + "|"
    rows = []
    for dimension in dimensions:
        values = []
        for subject in subjects:
            cell = cells.get((subject.id, dimension.id))
            if cell is None:
                values.append("—")
            elif cell.numeric_value is not None:
                values.append(f"{cell.numeric_value}{f' {dimension.unit}' if dimension.unit else ''}")
            elif cell.boolean_value is not None:
                values.append("yes" if cell.boolean_value else "no")
            else:
                values.append((cell.text_value or "—").replace("\n", " ").replace("|", "\\|"))
        rows.append(f"| **{dimension.name}** | " + " | ".join(values) + " |")

    return "\n".join(
        [
            _front_matter(
                {
                    "title": comparison.title,
                    "subject_type": comparison.subject_type,
                    "updated_at": comparison.updated_at.isoformat(),
                    "forge_id": comparison.id,
                }
            ),
            "",
            f"# {comparison.title}",
            "",
            comparison.description or "",
            "",
            header,
            divider,
            *rows,
            "",
        ]
    ).rstrip() + "\n"


def render_entity(session: Session, entity: Entity) -> str:
    neighbours = links.neighbours(session, TargetType.ENTITY, entity.id)
    mention_rows = session.execute(
        select(Source).join(EntityMention, EntityMention.source_id == Source.id).where(
            EntityMention.entity_id == entity.id
        )
    ).scalars().all()
    mention_lines = [f"- {s.title}" for s in mention_rows] or ["_(no sources)_"]
    link_lines = [f"- {n.relation} → {n.ref.label}" for n in neighbours] or ["_(none)_"]
    return "\n".join(
        [
            _front_matter({"name": entity.name, "kind": entity.kind, "forge_id": entity.id}),
            "",
            f"# {entity.name}",
            "",
            f"`{entity.kind}`",
            "",
            entity.description or "",
            "",
            "## Mentioned in",
            "",
            *mention_lines,
            "",
            "## Relationships",
            "",
            *link_lines,
            "",
        ]
    ).rstrip() + "\n"


# --- bundles ---------------------------------------------------------------


def dossier_bundle(session: Session, dossier: Dossier, *, include_sources: bool = True) -> bytes:
    """Zip with the dossier Markdown plus each linked source as Markdown."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{dossier.slug}/dossier.md", render_dossier(session, dossier))
        if include_sources:
            for source_id in dossier_service.linked_source_ids(session, dossier.id):
                source = session.get(Source, source_id)
                if source is None:
                    continue
                archive.writestr(
                    f"{dossier.slug}/sources/{slugify(source.title)}-{source.id[:8]}.md",
                    render_source(session, source),
                )
        knowledge_ids = [i.target_id for i in dossier.items if i.target_type == TargetType.KNOWLEDGE]
        for knowledge_id in knowledge_ids:
            obj = session.get(KnowledgeObject, knowledge_id)
            if obj is not None:
                archive.writestr(
                    f"{dossier.slug}/knowledge/{obj.kind}-{slugify(obj.title)}-{obj.id[:8]}.md",
                    render_knowledge(session, obj),
                )
        archive.writestr(
            f"{dossier.slug}/manifest.json",
            json.dumps(
                {
                    "exported_at": dt.datetime.now(dt.UTC).isoformat(),
                    "forge_version": __version__,
                    "dossier_id": dossier.id,
                    "slug": dossier.slug,
                },
                indent=2,
            ),
        )
    return buffer.getvalue()


def sources_bundle(
    session: Session, source_ids: list[str], *, include_originals: bool = True
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        included: list[dict[str, Any]] = []
        for source_id in source_ids:
            source = session.get(Source, source_id)
            if source is None:
                continue
            stem = f"{slugify(source.title)}-{source.id[:8]}"
            archive.writestr(f"sources/{stem}.md", render_source(session, source))
            included.append({"id": source.id, "title": source.title, "file": f"sources/{stem}.md"})
            if include_originals and source.storage_path and storage.blob_exists(source.storage_path):
                suffix = (source.original_filename or "").split(".")[-1]
                extension = f".{suffix}" if suffix and len(suffix) <= 8 else ""
                archive.writestr(
                    f"originals/{stem}{extension}", storage.read_blob(source.storage_path)
                )
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "exported_at": dt.datetime.now(dt.UTC).isoformat(),
                    "forge_version": __version__,
                    "sources": included,
                },
                indent=2,
            ),
        )
    return buffer.getvalue()


# --- JSON ------------------------------------------------------------------

def _serialize(value: Any) -> Any:
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes | bytearray):
        return base64.b64encode(bytes(value)).decode("ascii")
    return value


def json_dump(session: Session) -> dict[str, Any]:
    """Full data export (no binaries). Import-friendly and diff-friendly."""

    from ..models import (
        AppSetting,
        ClaimEvidence,
        Collection,
        CollectionItem,
        ComparisonCell,
        ComparisonDimension,
        ComparisonSubject,
        Document,
        DossierClaim,
        DossierItem,
        Generation,
        ImportBatch,
        KnowledgeExcerpt,
        Link,
        Tag,
        Tagging,
        TimelineEvent,
    )

    tables = {
        "import_batch": ImportBatch,
        "source": Source,
        "document": Document,
        "excerpt": Excerpt,
        "knowledge_object": KnowledgeObject,
        "knowledge_excerpt": KnowledgeExcerpt,
        "entity": Entity,
        "entity_mention": EntityMention,
        "tag": Tag,
        "tagging": Tagging,
        "collection": Collection,
        "collection_item": CollectionItem,
        "dossier": Dossier,
        "dossier_item": DossierItem,
        "dossier_claim": DossierClaim,
        "claim_evidence": ClaimEvidence,
        "timeline_event": TimelineEvent,
        "link": Link,
        "comparison": Comparison,
        "comparison_subject": ComparisonSubject,
        "comparison_dimension": ComparisonDimension,
        "comparison_cell": ComparisonCell,
        "generation": Generation,
        "app_setting": AppSetting,
    }
    payload: dict[str, Any] = {
        "format": "forge.json-export",
        "format_version": 1,
        "forge_version": __version__,
        "exported_at": dt.datetime.now(dt.UTC).isoformat(),
        "tables": {},
    }
    for name, model in tables.items():
        rows = session.execute(select(model)).scalars().all()
        payload["tables"][name] = [
            {
                column.name: _serialize(getattr(row, key))
                for key, column in model.__mapper__.columns.items()
            }
            for row in rows
        ]
    payload["counts"] = {name: len(rows) for name, rows in payload["tables"].items()}
    return payload
