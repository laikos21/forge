"""Domain vocabulary: the closed sets of values used across FORGE.

These live in one place so the API schemas, the seed data, the frontend
contract (exposed via ``GET /api/meta/vocabulary``) and the tests can never
drift apart. They are validated in Pydantic rather than as SQL ``CHECK``
constraints so that adding a value stays a code change, not a migration.
"""

from __future__ import annotations

from enum import StrEnum


class SourceKind(StrEnum):
    PDF = "pdf"
    TEXT = "text"
    MARKDOWN = "markdown"
    CSV = "csv"
    JSON = "json"
    TRANSCRIPT = "transcript"
    IMAGE = "image"
    NOTE = "note"
    WEB_ARTICLE = "web_article"


#: Source kinds that are produced by pasting text rather than uploading a file.
PASTE_KINDS = {SourceKind.TEXT, SourceKind.MARKDOWN, SourceKind.TRANSCRIPT, SourceKind.NOTE, SourceKind.WEB_ARTICLE}


class SourceStatus(StrEnum):
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"
    ERROR = "error"


class DocumentKind(StrEnum):
    PAGE = "page"
    SECTION = "section"
    SEGMENT = "segment"
    ROW_GROUP = "row_group"
    RECORD = "record"
    CHUNK = "chunk"
    WHOLE = "whole"


class KnowledgeKind(StrEnum):
    INSIGHT = "insight"
    RULE = "rule"
    HYPOTHESIS = "hypothesis"
    DECISION = "decision"
    QUOTE = "quote"
    NOTE = "note"


#: Allowed lifecycle values per knowledge kind. First entry is the default.
KNOWLEDGE_STATUSES: dict[str, list[str]] = {
    KnowledgeKind.INSIGHT: ["draft", "active", "archived"],
    KnowledgeKind.RULE: ["draft", "active", "under_review", "retired"],
    KnowledgeKind.HYPOTHESIS: ["open", "supported", "refuted", "inconclusive"],
    KnowledgeKind.DECISION: ["proposed", "made", "executed", "reviewed", "reversed"],
    KnowledgeKind.QUOTE: ["draft", "active", "archived"],
    KnowledgeKind.NOTE: ["draft", "active", "archived"],
}


class EntityKind(StrEnum):
    COMPANY = "company"
    TICKER = "ticker"
    PERSON = "person"
    TOPIC = "topic"
    THEME = "theme"


class DossierSubject(StrEnum):
    COMPANY = "company"
    INDUSTRY = "industry"
    SETUP = "setup"
    THEME = "theme"
    PROJECT = "project"
    PERSON = "person"
    OTHER = "other"


class DossierStatus(StrEnum):
    ACTIVE = "active"
    WATCHING = "watching"
    ARCHIVED = "archived"


class ClaimStance(StrEnum):
    BULL = "bull"
    BEAR = "bear"
    RISK = "risk"
    QUESTION = "question"
    NEUTRAL = "neutral"


class EvidenceStance(StrEnum):
    SUPPORTS = "supports"
    REFUTES = "refutes"
    CONTEXT = "context"


class Origin(StrEnum):
    USER = "user"
    IMPORT = "import"
    GENERATED = "generated"
    SEED = "seed"


class TargetType(StrEnum):
    """Polymorphic reference targets used by tags, links and collections."""

    SOURCE = "source"
    DOCUMENT = "document"
    EXCERPT = "excerpt"
    KNOWLEDGE = "knowledge"
    ENTITY = "entity"
    DOSSIER = "dossier"
    COLLECTION = "collection"
    COMPARISON = "comparison"


class DimensionKind(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    RATING = "rating"
    BOOLEAN = "boolean"


#: Relation vocabulary for the generic link table. ``None`` means the relation is
#: symmetric and is presented identically from both ends.
RELATION_INVERSES: dict[str, str | None] = {
    "related_to": None,
    "contradicts": None,
    "supports": "supported_by",
    "supported_by": "supports",
    "refutes": "refuted_by",
    "refuted_by": "refutes",
    "derived_from": "produced",
    "produced": "derived_from",
    "mentions": "mentioned_in",
    "mentioned_in": "mentions",
    "ticker_of": "has_ticker",
    "has_ticker": "ticker_of",
    "competitor_of": None,
    "supplier_of": "customer_of",
    "customer_of": "supplier_of",
    "part_of": "contains",
    "contains": "part_of",
    "follows_up": "followed_up_by",
    "followed_up_by": "follows_up",
    "authored_by": "authored",
    "authored": "authored_by",
}

SYMMETRIC_RELATIONS = {name for name, inverse in RELATION_INVERSES.items() if inverse is None}


def inverse_relation(relation: str) -> str:
    """Return the relation label seen from the other end of the edge."""

    return RELATION_INVERSES.get(relation) or relation


#: File extensions accepted by the uploader, mapped to their source kind.
EXTENSION_KINDS: dict[str, SourceKind] = {
    ".pdf": SourceKind.PDF,
    ".txt": SourceKind.TEXT,
    ".text": SourceKind.TEXT,
    ".log": SourceKind.TEXT,
    ".vtt": SourceKind.TRANSCRIPT,
    ".srt": SourceKind.TRANSCRIPT,
    ".md": SourceKind.MARKDOWN,
    ".markdown": SourceKind.MARKDOWN,
    ".csv": SourceKind.CSV,
    ".tsv": SourceKind.CSV,
    ".json": SourceKind.JSON,
    ".jsonl": SourceKind.JSON,
    ".png": SourceKind.IMAGE,
    ".jpg": SourceKind.IMAGE,
    ".jpeg": SourceKind.IMAGE,
    ".gif": SourceKind.IMAGE,
    ".webp": SourceKind.IMAGE,
    ".bmp": SourceKind.IMAGE,
    ".tif": SourceKind.IMAGE,
    ".tiff": SourceKind.IMAGE,
}

IMAGE_EXTENSIONS = {ext for ext, kind in EXTENSION_KINDS.items() if kind is SourceKind.IMAGE}


def vocabulary() -> dict[str, object]:
    """Machine-readable vocabulary served to the frontend."""

    return {
        "source_kinds": [k.value for k in SourceKind],
        "source_statuses": [s.value for s in SourceStatus],
        "document_kinds": [k.value for k in DocumentKind],
        "knowledge_kinds": [k.value for k in KnowledgeKind],
        "knowledge_statuses": {k: v for k, v in KNOWLEDGE_STATUSES.items()},
        "entity_kinds": [k.value for k in EntityKind],
        "dossier_subjects": [k.value for k in DossierSubject],
        "dossier_statuses": [k.value for k in DossierStatus],
        "claim_stances": [k.value for k in ClaimStance],
        "evidence_stances": [k.value for k in EvidenceStance],
        "target_types": [k.value for k in TargetType],
        "dimension_kinds": [k.value for k in DimensionKind],
        "relations": sorted(RELATION_INVERSES),
        "symmetric_relations": sorted(SYMMETRIC_RELATIONS),
        "accepted_extensions": sorted(EXTENSION_KINDS),
    }
