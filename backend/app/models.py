"""SQLAlchemy ORM models.

Design notes (the reasoning lives in ``DATA_MODEL.md``):

* Identifiers are UUID4 strings. They are stable across backup/restore and let
  the frontend create optimistic references without a round-trip.
* Knowledge objects (insight / rule / hypothesis / decision / quote / note) share
  one table with a ``kind`` discriminator plus a small ``data_json`` payload for
  kind-specific fields. They share ~90% of their columns and all of their
  linking behaviour, so five near-identical tables would buy nothing.
* Cross-cutting associations (tags, links, collection items, dossier items) are
  polymorphic ``(target_type, target_id)`` pairs. SQLite cannot enforce those as
  foreign keys; integrity is enforced in the service layer and by the
  ``/api/maintenance/integrity`` check.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .types import DecimalText, IsoDate, UtcDateTime, utcnow


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    type_annotation_map = {
        dt.datetime: UtcDateTime,
        dt.date: IsoDate,
        Decimal: DecimalText,
        dict[str, Any]: JSON,
        list[str]: JSON,
    }


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# Sources and their extracted content
# ---------------------------------------------------------------------------


class ImportBatch(Base):
    __tablename__ = "import_batch"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    label: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    sources: Mapped[list[Source]] = relationship(back_populates="batch")


class Source(Base, TimestampMixin):
    __tablename__ = "source"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="processing")

    title: Mapped[str] = mapped_column(String(500), nullable=False, default="Untitled source")
    author: Mapped[str | None] = mapped_column(String(300))
    publisher: Mapped[str | None] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    published_on: Mapped[dt.date | None] = mapped_column(IsoDate)
    language: Mapped[str | None] = mapped_column(String(8))
    summary: Mapped[str | None] = mapped_column(Text)

    original_filename: Mapped[str | None] = mapped_column(String(400))
    storage_path: Mapped[str | None] = mapped_column(String(500))
    mime_type: Mapped[str | None] = mapped_column(String(160))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    text_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int | None] = mapped_column(Integer)

    extraction_method: Mapped[str] = mapped_column(String(64), default="unknown")
    extraction_warnings: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    detected_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    meta: Mapped[dict[str, Any]] = mapped_column("meta_json", JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    review_notes: Mapped[str | None] = mapped_column(Text)

    origin: Mapped[str] = mapped_column(String(16), default="import")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    imported_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)

    batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batch.id", ondelete="SET NULL"))
    duplicate_of_id: Mapped[str | None] = mapped_column(ForeignKey("source.id", ondelete="SET NULL"))

    batch: Mapped[ImportBatch | None] = relationship(back_populates="sources")
    documents: Mapped[list[Document]] = relationship(
        back_populates="source", cascade="all, delete-orphan", order_by="Document.ordinal"
    )
    excerpts: Mapped[list[Excerpt]] = relationship(
        back_populates="source", cascade="all, delete-orphan", order_by="Excerpt.char_start"
    )


class Document(Base):
    """A structural unit inside a source: a PDF page, a Markdown section, a
    transcript segment, a group of CSV rows."""

    __tablename__ = "document"
    __table_args__ = (
        Index("ix_document_source_ordinal", "source_id", "ordinal"),
        UniqueConstraint("source_id", "ordinal", name="uq_document_source_ordinal"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="chunk")
    title: Mapped[str | None] = mapped_column(String(400))
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    locator: Mapped[dict[str, Any]] = mapped_column("locator_json", JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    source: Mapped[Source] = relationship(back_populates="documents")
    excerpts: Mapped[list[Excerpt]] = relationship(back_populates="document")


class Excerpt(Base, TimestampMixin):
    """A verbatim span of a source, with the provenance needed to find it again."""

    __tablename__ = "excerpt"
    __table_args__ = (Index("ix_excerpt_source", "source_id", "char_start"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("document.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    locator: Mapped[dict[str, Any]] = mapped_column("locator_json", JSON, default=dict)
    origin: Mapped[str] = mapped_column(String(16), default="user")
    created_via: Mapped[str] = mapped_column(String(64), default="manual_selection")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    source: Mapped[Source] = relationship(back_populates="excerpts")
    document: Mapped[Document | None] = relationship(back_populates="excerpts")
    knowledge_links: Mapped[list[KnowledgeExcerpt]] = relationship(
        back_populates="excerpt", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Knowledge objects
# ---------------------------------------------------------------------------


class KnowledgeObject(Base, TimestampMixin):
    __tablename__ = "knowledge_object"
    __table_args__ = (Index("ix_knowledge_kind_status", "kind", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    confidence: Mapped[int | None] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String(16), default="user", index=True)
    generated_by: Mapped[str | None] = mapped_column(String(160))
    generation_id: Mapped[str | None] = mapped_column(String(36))
    review_due_on: Mapped[dt.date | None] = mapped_column(IsoDate, index=True)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    outcome: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column("data_json", JSON, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    excerpt_links: Mapped[list[KnowledgeExcerpt]] = relationship(
        back_populates="knowledge", cascade="all, delete-orphan"
    )


class KnowledgeExcerpt(Base):
    """Evidence edge: which excerpt backs (or undercuts) which knowledge object."""

    __tablename__ = "knowledge_excerpt"
    __table_args__ = (
        UniqueConstraint("knowledge_id", "excerpt_id", name="uq_knowledge_excerpt"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_object.id", ondelete="CASCADE"), nullable=False
    )
    excerpt_id: Mapped[str] = mapped_column(ForeignKey("excerpt.id", ondelete="CASCADE"), nullable=False)
    stance: Mapped[str] = mapped_column(String(16), default="supports")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    knowledge: Mapped[KnowledgeObject] = relationship(back_populates="excerpt_links")
    excerpt: Mapped[Excerpt] = relationship(back_populates="knowledge_links")


# ---------------------------------------------------------------------------
# Entities, tags, collections
# ---------------------------------------------------------------------------


class Entity(Base, TimestampMixin):
    __tablename__ = "entity"
    __table_args__ = (
        UniqueConstraint("kind", "normalized_name", name="uq_entity_kind_name"),
        Index("ix_entity_kind", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column("aliases_json", JSON, default=list)
    data: Mapped[dict[str, Any]] = mapped_column("data_json", JSON, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class EntityMention(Base):
    """A confirmed or candidate appearance of an entity inside a source."""

    __tablename__ = "entity_mention"
    __table_args__ = (
        UniqueConstraint("entity_id", "source_id", name="uq_entity_mention"),
        Index("ix_entity_mention_source", "source_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entity.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id", ondelete="CASCADE"), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=1)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    detector: Mapped[str] = mapped_column(String(64), default="user")
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    entity: Mapped[Entity] = relationship()


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    color: Mapped[str | None] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)


class Tagging(Base):
    __tablename__ = "tagging"
    __table_args__ = (
        UniqueConstraint("tag_id", "target_type", "target_id", name="uq_tagging"),
        Index("ix_tagging_target", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tag.id", ondelete="CASCADE"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    tag: Mapped[Tag] = relationship()


class Collection(Base, TimestampMixin):
    __tablename__ = "collection"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    items: Mapped[list[CollectionItem]] = relationship(
        back_populates="collection", cascade="all, delete-orphan", order_by="CollectionItem.position"
    )


class CollectionItem(Base):
    __tablename__ = "collection_item"
    __table_args__ = (
        UniqueConstraint("collection_id", "target_type", "target_id", name="uq_collection_item"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collection.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    collection: Mapped[Collection] = relationship(back_populates="items")


# ---------------------------------------------------------------------------
# Dossiers
# ---------------------------------------------------------------------------


class Dossier(Base, TimestampMixin):
    __tablename__ = "dossier"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    overview: Mapped[str] = mapped_column(Text, default="")
    thesis: Mapped[str] = mapped_column(Text, default="")
    bull_case: Mapped[str] = mapped_column(Text, default="")
    bear_case: Mapped[str] = mapped_column(Text, default="")
    risks: Mapped[str] = mapped_column(Text, default="")
    open_questions: Mapped[str] = mapped_column(Text, default="")
    primary_entity_id: Mapped[str | None] = mapped_column(ForeignKey("entity.id", ondelete="SET NULL"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    primary_entity: Mapped[Entity | None] = relationship()
    items: Mapped[list[DossierItem]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan", order_by="DossierItem.position"
    )
    claims: Mapped[list[DossierClaim]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan", order_by="DossierClaim.position"
    )
    events: Mapped[list[TimelineEvent]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan", order_by="TimelineEvent.occurred_on"
    )


class DossierItem(Base):
    __tablename__ = "dossier_item"
    __table_args__ = (
        UniqueConstraint("dossier_id", "target_type", "target_id", name="uq_dossier_item"),
        Index("ix_dossier_item_target", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(ForeignKey("dossier.id", ondelete="CASCADE"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    section: Mapped[str] = mapped_column(String(48), default="sources")
    position: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    dossier: Mapped[Dossier] = relationship(back_populates="items")


class DossierClaim(Base, TimestampMixin):
    __tablename__ = "dossier_claim"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(ForeignKey("dossier.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    stance: Mapped[str] = mapped_column(String(16), default="neutral")
    confidence: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="open")
    position: Mapped[int] = mapped_column(Integer, default=0)
    origin: Mapped[str] = mapped_column(String(16), default="user")
    generated_by: Mapped[str | None] = mapped_column(String(160))

    dossier: Mapped[Dossier] = relationship(back_populates="claims")
    evidence: Mapped[list[ClaimEvidence]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("dossier_claim.id", ondelete="CASCADE"), nullable=False)
    excerpt_id: Mapped[str | None] = mapped_column(ForeignKey("excerpt.id", ondelete="CASCADE"))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id", ondelete="CASCADE"))
    stance: Mapped[str] = mapped_column(String(16), default="supports")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    claim: Mapped[DossierClaim] = relationship(back_populates="evidence")
    excerpt: Mapped[Excerpt | None] = relationship()


class TimelineEvent(Base):
    __tablename__ = "timeline_event"
    __table_args__ = (Index("ix_timeline_dossier_date", "dossier_id", "occurred_on"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(ForeignKey("dossier.id", ondelete="CASCADE"), nullable=False)
    occurred_on: Mapped[dt.date] = mapped_column(IsoDate, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(48), default="event")
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    dossier: Mapped[Dossier] = relationship(back_populates="events")


# ---------------------------------------------------------------------------
# Generic relationships
# ---------------------------------------------------------------------------


class Link(Base):
    """Directed edge between any two objects, presented bidirectionally."""

    __tablename__ = "link"
    __table_args__ = (
        UniqueConstraint(
            "from_type", "from_id", "to_type", "to_id", "relation", name="uq_link_edge"
        ),
        Index("ix_link_from", "from_type", "from_id"),
        Index("ix_link_to", "to_type", "to_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    from_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_id: Mapped[str] = mapped_column(String(36), nullable=False)
    to_type: Mapped[str] = mapped_column(String(32), nullable=False)
    to_id: Mapped[str] = mapped_column(String(36), nullable=False)
    relation: Mapped[str] = mapped_column(String(48), nullable=False, default="related_to")
    note: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16), default="user")
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Comparison workspace
# ---------------------------------------------------------------------------


class Comparison(Base, TimestampMixin):
    __tablename__ = "comparison"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False, default="entity")
    description: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    subjects: Mapped[list[ComparisonSubject]] = relationship(
        back_populates="comparison", cascade="all, delete-orphan", order_by="ComparisonSubject.position"
    )
    dimensions: Mapped[list[ComparisonDimension]] = relationship(
        back_populates="comparison", cascade="all, delete-orphan", order_by="ComparisonDimension.position"
    )
    cells: Mapped[list[ComparisonCell]] = relationship(
        back_populates="comparison", cascade="all, delete-orphan"
    )


class ComparisonSubject(Base):
    __tablename__ = "comparison_subject"
    __table_args__ = (
        UniqueConstraint("comparison_id", "target_type", "target_id", name="uq_comparison_subject"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    comparison_id: Mapped[str] = mapped_column(
        ForeignKey("comparison.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    label: Mapped[str] = mapped_column(String(200), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)

    comparison: Mapped[Comparison] = relationship(back_populates="subjects")


class ComparisonDimension(Base):
    __tablename__ = "comparison_dimension"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    comparison_id: Mapped[str] = mapped_column(
        ForeignKey("comparison.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="text")
    unit: Mapped[str | None] = mapped_column(String(32))
    higher_is_better: Mapped[bool] = mapped_column(Boolean, default=True)
    weight: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("1"))
    position: Mapped[int] = mapped_column(Integer, default=0)

    comparison: Mapped[Comparison] = relationship(back_populates="dimensions")


class ComparisonCell(Base, TimestampMixin):
    __tablename__ = "comparison_cell"
    __table_args__ = (UniqueConstraint("subject_id", "dimension_id", name="uq_comparison_cell"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    comparison_id: Mapped[str] = mapped_column(
        ForeignKey("comparison.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[str] = mapped_column(
        ForeignKey("comparison_subject.id", ondelete="CASCADE"), nullable=False
    )
    dimension_id: Mapped[str] = mapped_column(
        ForeignKey("comparison_dimension.id", ondelete="CASCADE"), nullable=False
    )
    text_value: Mapped[str | None] = mapped_column(Text)
    numeric_value: Mapped[Decimal | None] = mapped_column(DecimalText)
    boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    excerpt_id: Mapped[str | None] = mapped_column(ForeignKey("excerpt.id", ondelete="SET NULL"))
    origin: Mapped[str] = mapped_column(String(16), default="user")

    comparison: Mapped[Comparison] = relationship(back_populates="cells")


# ---------------------------------------------------------------------------
# Optional local intelligence + preferences
# ---------------------------------------------------------------------------


class Generation(Base):
    """Audit record for every optional-LLM call. Nothing generated is stored
    anywhere else without a row here to point back at."""

    __tablename__ = "generation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(48), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    operation: Mapped[str] = mapped_column(String(48), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(36))
    prompt: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[str] = mapped_column(Text, default="")
    parsed: Mapped[dict[str, Any]] = mapped_column("parsed_json", JSON, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)


class Embedding(Base):
    """Optional local semantic index. Empty and unused when disabled."""

    __tablename__ = "embedding"
    __table_args__ = (
        UniqueConstraint("ref_type", "ref_id", "model", name="uq_embedding_ref"),
        Index("ix_embedding_model", "model"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ref_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(36), index=True)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[bytes] = mapped_column(nullable=False)
    norm: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)


class AppSetting(Base):
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column("value_json", JSON, default=dict)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
