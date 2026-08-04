"""Pydantic request/response models.

Request bodies are strictly validated (``extra="forbid"``) so a typo in a field
name fails loudly instead of being silently ignored. Responses are permissive
models built from ORM objects.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain import (
    KNOWLEDGE_STATUSES,
    ClaimStance,
    DimensionKind,
    DossierStatus,
    DossierSubject,
    EntityKind,
    EvidenceStance,
    KnowledgeKind,
    SourceKind,
    SourceStatus,
    TargetType,
)

NonEmptyStr = Annotated[str, Field(min_length=1, max_length=2000)]
Title = Annotated[str, Field(min_length=1, max_length=400)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- import ----------------------------------------------------------------


class TextImportRequest(StrictModel):
    text: Annotated[str, Field(min_length=1)]
    kind: SourceKind | None = None
    title: str | None = Field(default=None, max_length=400)
    author: str | None = Field(default=None, max_length=300)
    source_url: str | None = Field(default=None, max_length=2000)
    published_on: dt.date | None = None
    filename: str | None = Field(default=None, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=40)
    force: bool = False
    batch_label: str | None = Field(default=None, max_length=200)


class ImportItemResult(BaseModel):
    status: Literal["created", "duplicate", "error", "rejected"]
    filename: str | None = None
    source_id: str | None = None
    title: str | None = None
    message: str = ""
    warnings: list[str] = Field(default_factory=list)
    duplicate_of_id: str | None = None
    duplicate_of_title: str | None = None


class ImportResponse(BaseModel):
    batch_id: str | None = None
    created: int = 0
    duplicates: int = 0
    errors: int = 0
    rejected: int = 0
    results: list[ImportItemResult] = Field(default_factory=list)


class EntityCandidateIn(StrictModel):
    kind: EntityKind
    name: Annotated[str, Field(min_length=1, max_length=300)]
    count: int = 1
    detector: str = "user"
    confidence: str | None = None
    evidence: str | None = None
    grounded: bool | None = None
    existing_id: str | None = None


class ReviewRequest(StrictModel):
    title: str | None = Field(default=None, max_length=400)
    author: str | None = Field(default=None, max_length=300)
    publisher: str | None = Field(default=None, max_length=300)
    source_url: str | None = Field(default=None, max_length=2000)
    published_on: dt.date | None = None
    language: str | None = Field(default=None, max_length=8)
    summary: str | None = None
    review_notes: str | None = None
    tags: list[str] | None = Field(default=None, max_length=40)
    confirmed_entities: list[EntityCandidateIn] = Field(default_factory=list)


# --- sources ---------------------------------------------------------------


class SourceUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=400)
    author: str | None = Field(default=None, max_length=300)
    publisher: str | None = Field(default=None, max_length=300)
    source_url: str | None = Field(default=None, max_length=2000)
    published_on: dt.date | None = None
    language: str | None = Field(default=None, max_length=8)
    summary: str | None = None
    review_notes: str | None = None
    status: SourceStatus | None = None
    kind: SourceKind | None = None


class TagSummary(ORMModel):
    id: str
    slug: str
    name: str
    color: str | None = None


class SourceSummary(ORMModel):
    id: str
    kind: str
    status: str
    title: str
    author: str | None = None
    publisher: str | None = None
    source_url: str | None = None
    published_on: dt.date | None = None
    language: str | None = None
    summary: str | None = None
    original_filename: str | None = None
    mime_type: str | None = None
    byte_size: int | None = None
    char_count: int = 0
    word_count: int = 0
    page_count: int | None = None
    imported_at: dt.datetime
    updated_at: dt.datetime
    reviewed_at: dt.datetime | None = None
    is_demo: bool = False
    extraction_method: str = ""
    error_message: str | None = None
    content_hash: str = ""
    tags: list[TagSummary] = Field(default_factory=list)
    excerpt_count: int = 0
    has_original: bool = False


class DocumentOut(ORMModel):
    id: str
    ordinal: int
    kind: str
    title: str | None = None
    text: str
    char_start: int
    char_end: int
    locator: dict[str, Any] = Field(default_factory=dict)
    locator_label: str = ""


class ExcerptCreate(StrictModel):
    text: NonEmptyStr
    document_id: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    note: str | None = None
    locator: dict[str, Any] | None = None

    @model_validator(mode="after")
    def check_range(self) -> ExcerptCreate:
        if self.char_start is not None and self.char_end is not None and self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self


class ExcerptUpdate(StrictModel):
    text: str | None = Field(default=None, min_length=1)
    note: str | None = None


class ExcerptOut(ORMModel):
    id: str
    source_id: str
    document_id: str | None = None
    text: str
    note: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    locator: dict[str, Any] = Field(default_factory=dict)
    origin: str = "user"
    created_at: dt.datetime
    provenance: dict[str, Any] = Field(default_factory=dict)
    used_by: list[dict[str, Any]] = Field(default_factory=list)


class TagsPut(StrictModel):
    tags: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(default_factory=list, max_length=60)


# --- knowledge -------------------------------------------------------------


class KnowledgeCreate(StrictModel):
    kind: KnowledgeKind
    title: Title
    body: str = ""
    status: str | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    review_due_on: dt.date | None = None
    outcome: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=40)
    excerpt_ids: list[str] = Field(default_factory=list, max_length=100)
    origin: Literal["user", "generated"] = "user"
    generated_by: str | None = None
    generation_id: str | None = None

    @model_validator(mode="after")
    def check_status(self) -> KnowledgeCreate:
        allowed = KNOWLEDGE_STATUSES[self.kind]
        if self.status is None:
            self.status = allowed[0]
        elif self.status not in allowed:
            raise ValueError(f"status must be one of {allowed} for kind {self.kind}")
        return self


class KnowledgeUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=400)
    body: str | None = None
    status: str | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    review_due_on: dt.date | None = None
    resolved: bool | None = None
    outcome: str | None = None
    data: dict[str, Any] | None = None


class EvidenceCreate(StrictModel):
    excerpt_id: str
    stance: EvidenceStance = EvidenceStance.SUPPORTS
    note: str | None = None


class KnowledgeOut(ORMModel):
    id: str
    kind: str
    title: str
    body: str
    status: str
    confidence: int | None = None
    origin: str
    generated_by: str | None = None
    generation_id: str | None = None
    review_due_on: dt.date | None = None
    resolved_at: dt.datetime | None = None
    outcome: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    is_demo: bool = False
    created_at: dt.datetime
    updated_at: dt.datetime
    tags: list[TagSummary] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class PromoteExcerpt(StrictModel):
    kind: KnowledgeKind
    title: Title
    body: str = ""
    stance: EvidenceStance = EvidenceStance.SUPPORTS
    tags: list[str] = Field(default_factory=list, max_length=40)
    dossier_id: str | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)


# --- entities, tags, links -------------------------------------------------


class EntityCreate(StrictModel):
    kind: EntityKind
    name: Annotated[str, Field(min_length=1, max_length=300)]
    description: str | None = None
    aliases: list[str] = Field(default_factory=list, max_length=30)
    data: dict[str, Any] = Field(default_factory=dict)


class EntityUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    aliases: list[str] | None = None
    data: dict[str, Any] | None = None


class EntityOut(ORMModel):
    id: str
    kind: str
    name: str
    normalized_name: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    is_demo: bool = False
    created_at: dt.datetime
    source_count: int = 0


class TagCreate(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    color: str | None = Field(default=None, max_length=16)
    description: str | None = None


class TagOut(ORMModel):
    id: str
    slug: str
    name: str
    color: str | None = None
    description: str | None = None
    usage_count: int = 0


class LinkCreate(StrictModel):
    from_type: TargetType
    from_id: str
    to_type: TargetType
    to_id: str
    relation: str = "related_to"
    note: str | None = None


class CollectionCreate(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: str | None = None


class CollectionItemCreate(StrictModel):
    target_type: TargetType
    target_id: str
    note: str | None = None


# --- dossiers --------------------------------------------------------------


class DossierCreate(StrictModel):
    title: Title
    subject_kind: DossierSubject = DossierSubject.OTHER
    overview: str = ""
    thesis: str = ""
    bull_case: str = ""
    bear_case: str = ""
    risks: str = ""
    open_questions: str = ""
    status: DossierStatus = DossierStatus.ACTIVE
    primary_entity_id: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=40)


class DossierUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    subject_kind: DossierSubject | None = None
    overview: str | None = None
    thesis: str | None = None
    bull_case: str | None = None
    bear_case: str | None = None
    risks: str | None = None
    open_questions: str | None = None
    status: DossierStatus | None = None
    primary_entity_id: str | None = None


class DossierItemCreate(StrictModel):
    target_type: TargetType
    target_id: str
    section: Literal["sources", "evidence", "knowledge", "entities", "notes", "watchlist"] = "sources"
    note: str | None = None


class ClaimCreate(StrictModel):
    text: NonEmptyStr
    stance: ClaimStance = ClaimStance.NEUTRAL
    confidence: int | None = Field(default=None, ge=0, le=100)
    origin: Literal["user", "generated"] = "user"
    generated_by: str | None = None


class ClaimUpdate(StrictModel):
    text: str | None = Field(default=None, min_length=1)
    stance: ClaimStance | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    status: str | None = None
    position: int | None = None


class ClaimEvidenceCreate(StrictModel):
    excerpt_id: str | None = None
    source_id: str | None = None
    stance: EvidenceStance = EvidenceStance.SUPPORTS
    note: str | None = None

    @model_validator(mode="after")
    def check_target(self) -> ClaimEvidenceCreate:
        if not self.excerpt_id and not self.source_id:
            raise ValueError("provide excerpt_id or source_id")
        return self


class TimelineEventCreate(StrictModel):
    occurred_on: dt.date
    title: Title
    description: str | None = None
    kind: str = Field(default="event", max_length=48)
    source_id: str | None = None


class DossierSummary(ORMModel):
    id: str
    slug: str
    title: str
    subject_kind: str
    status: str
    overview: str = ""
    updated_at: dt.datetime
    created_at: dt.datetime
    is_demo: bool = False
    tags: list[TagSummary] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


# --- comparisons -----------------------------------------------------------


class ComparisonCreate(StrictModel):
    title: Title
    subject_type: TargetType = TargetType.ENTITY
    description: str | None = None
    dimensions: list[str] = Field(default_factory=list, max_length=40)


class ComparisonUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None


class ComparisonSubjectCreate(StrictModel):
    target_type: TargetType
    target_id: str
    label: str | None = Field(default=None, max_length=200)


class DimensionCreate(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    kind: DimensionKind = DimensionKind.TEXT
    unit: str | None = Field(default=None, max_length=32)
    higher_is_better: bool = True
    weight: Decimal = Decimal("1")


class DimensionUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: DimensionKind | None = None
    unit: str | None = None
    higher_is_better: bool | None = None
    weight: Decimal | None = None
    position: int | None = None


class CellUpsert(StrictModel):
    subject_id: str
    dimension_id: str
    text_value: str | None = None
    numeric_value: Decimal | None = None
    boolean_value: bool | None = None
    excerpt_id: str | None = None
    origin: Literal["user", "generated"] = "user"


# --- settings, intelligence, backups ---------------------------------------


class SettingsUpdate(StrictModel):
    values: dict[str, Any]

    @field_validator("values")
    @classmethod
    def not_empty(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("no settings supplied")
        return value


class IntelligenceRequest(StrictModel):
    operation: Literal[
        "summarize", "extract_entities", "suggest_topics", "extract_claims",
        "generate_questions", "draft_comparison",
    ]
    source_id: str | None = None
    dossier_id: str | None = None
    subjects: list[dict[str, Any]] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    title: str | None = None

    @model_validator(mode="after")
    def check_target(self) -> IntelligenceRequest:
        needs_source = {"summarize", "extract_entities", "suggest_topics", "extract_claims"}
        if self.operation in needs_source and not self.source_id:
            raise ValueError(f"{self.operation} requires source_id")
        if self.operation == "generate_questions" and not self.dossier_id:
            raise ValueError("generate_questions requires dossier_id")
        if self.operation == "draft_comparison" and (not self.subjects or not self.dimensions):
            raise ValueError("draft_comparison requires subjects and dimensions")
        return self


class BackupCreate(StrictModel):
    label: str | None = Field(default=None, max_length=40)


class ExportSourcesRequest(StrictModel):
    source_ids: list[str] = Field(min_length=1, max_length=500)
    include_originals: bool = True


class SeedRequest(StrictModel):
    reset: bool = False
