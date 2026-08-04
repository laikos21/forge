"""Optional-intelligence operations with deterministic fallbacks.

Each operation returns a :class:`OperationOutput` describing *how* it was
produced (``deterministic`` or ``generated``), what it was produced from
(source ids and excerpt ids), and a draft the user can edit and accept. Nothing
is written to a user-facing field here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ...lib.text import extractive_summary, split_sentences, top_keywords
from ...models import Dossier, Generation, KnowledgeObject, Source
from ..entities import detect_candidates
from .base import LLMProvider, LLMUnavailable

MAX_CONTEXT_CHARS = 12000

SYSTEM_PROMPT = (
    "You are a research assistant working inside a local knowledge base. "
    "Use ONLY the supplied text. Never add facts, numbers or names that are not present. "
    "If the text does not support an answer, say so. Reply with JSON only, no commentary."
)

CLAIM_MARKERS = re.compile(
    r"\b(will|should|expects?|expected|because|therefore|implies|suggests?|indicates?|"
    r"grew|fell|rose|declined|increase[sd]?|decrease[sd]?|margin|guidance|revenue|risk|"
    r"probable|likely|unlikely|driver|catalyst|thesis)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class OperationOutput:
    operation: str
    method: str  # deterministic | generated
    provider: str
    model: str | None
    items: list[dict[str, Any]] = field(default_factory=list)
    text: str = ""
    notice: str = ""
    generation_id: str | None = None
    sources: list[str] = field(default_factory=list)
    fallback_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "method": self.method,
            "generated": self.method == "generated",
            "provider": self.provider,
            "model": self.model,
            "items": self.items,
            "text": self.text,
            "notice": self.notice,
            "generation_id": self.generation_id,
            "sources": self.sources,
            "fallback_reason": self.fallback_reason,
        }


def _context(source: Source) -> str:
    text = source.text or ""
    if len(text) <= MAX_CONTEXT_CHARS:
        return text
    head = text[: int(MAX_CONTEXT_CHARS * 0.7)]
    tail = text[-int(MAX_CONTEXT_CHARS * 0.3) :]
    return f"{head}\n\n[… {len(text) - MAX_CONTEXT_CHARS:,} characters omitted …]\n\n{tail}"


def _parse_json(text: str) -> Any:
    """Extract the first JSON value from a model response."""

    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("model response was not valid JSON")


def _record(
    session: Session,
    *,
    operation: str,
    provider: str,
    model: str,
    prompt: str,
    output: str,
    parsed: Any,
    duration_ms: int,
    target_type: str | None,
    target_id: str | None,
) -> Generation:
    generation = Generation(
        provider=provider,
        model=model,
        operation=operation,
        target_type=target_type,
        target_id=target_id,
        prompt=prompt,
        output=output,
        parsed=parsed if isinstance(parsed, dict) else {"items": parsed},
        duration_ms=duration_ms,
    )
    session.add(generation)
    session.flush()
    return generation


def _try_generate(
    session: Session,
    provider: LLMProvider | None,
    *,
    operation: str,
    prompt: str,
    target_type: str | None,
    target_id: str | None,
) -> tuple[Any, Generation] | tuple[None, str]:
    if provider is None:
        return None, "Local LLM features are disabled."
    try:
        result = provider.complete(prompt, system=SYSTEM_PROMPT)
    except LLMUnavailable as exc:
        return None, str(exc)
    try:
        parsed = _parse_json(result.text)
    except ValueError as exc:
        return None, f"{exc} (model {result.model})"
    generation = _record(
        session,
        operation=operation,
        provider=result.provider,
        model=result.model,
        prompt=prompt,
        output=result.text,
        parsed=parsed,
        duration_ms=result.duration_ms,
        target_type=target_type,
        target_id=target_id,
    )
    return parsed, generation


# --- operations ------------------------------------------------------------


def summarize_source(session: Session, source: Source, provider: LLMProvider | None) -> OperationOutput:
    prompt = (
        "Summarise the following document in at most 6 sentences for a research analyst. "
        'Reply as {"summary": "...", "key_points": ["...", "..."]}.\n\n'
        f"TITLE: {source.title}\n\nTEXT:\n{_context(source)}"
    )
    parsed, meta = _try_generate(
        session, provider, operation="summarize", prompt=prompt,
        target_type="source", target_id=source.id,
    )
    if parsed is not None and isinstance(meta, Generation):
        summary = str(parsed.get("summary", "")).strip() if isinstance(parsed, dict) else ""
        points = parsed.get("key_points", []) if isinstance(parsed, dict) else []
        return OperationOutput(
            operation="summarize",
            method="generated",
            provider=meta.provider,
            model=meta.model,
            text=summary,
            items=[{"text": str(p)} for p in points if str(p).strip()],
            notice="Model-generated draft. Verify against the source before accepting.",
            generation_id=meta.id,
            sources=[source.id],
        )
    return OperationOutput(
        operation="summarize",
        method="deterministic",
        provider="forge",
        model=None,
        text=extractive_summary(source.text, max_sentences=4, max_chars=900),
        items=[{"text": f"{word} ({count})"} for word, count in top_keywords(source.text, limit=8)],
        notice="Sentences copied verbatim from the source (extractive, no model).",
        sources=[source.id],
        fallback_reason=meta if isinstance(meta, str) else None,
    )


def extract_entities(session: Session, source: Source, provider: LLMProvider | None) -> OperationOutput:
    prompt = (
        "List the companies, tickers, people, topics and themes explicitly named in the text. "
        'Reply as {"entities": [{"kind": "company|ticker|person|topic|theme", "name": "...", '
        '"evidence": "short quote from the text"}]}. Do not invent entities.\n\n'
        f"TEXT:\n{_context(source)}"
    )
    parsed, meta = _try_generate(
        session, provider, operation="extract_entities", prompt=prompt,
        target_type="source", target_id=source.id,
    )
    if parsed is not None and isinstance(meta, Generation):
        raw = parsed.get("entities", []) if isinstance(parsed, dict) else parsed
        items = []
        for entry in raw if isinstance(raw, list) else []:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            kind = str(entry.get("kind", "topic")).lower()
            if kind not in {"company", "ticker", "person", "topic", "theme"}:
                kind = "topic"
            evidence = str(entry.get("evidence", "")).strip()
            grounded = bool(evidence) and evidence[:60].lower() in (source.text or "").lower()
            items.append(
                {
                    "kind": kind,
                    "name": str(entry["name"]).strip(),
                    "evidence": evidence,
                    "grounded": grounded,
                    "confidence": "medium",
                    "detector": f"llm:{meta.model}",
                }
            )
        return OperationOutput(
            operation="extract_entities",
            method="generated",
            provider=meta.provider,
            model=meta.model,
            items=items,
            notice="Model-suggested entities. 'grounded' marks the ones whose quote was found in the text.",
            generation_id=meta.id,
            sources=[source.id],
        )
    candidates = detect_candidates(session, source.text or "", source.detected_metadata or {})
    return OperationOutput(
        operation="extract_entities",
        method="deterministic",
        provider="forge",
        model=None,
        items=[{**c.as_dict(), "grounded": True, "evidence": ""} for c in candidates],
        notice="Pattern-based detection (tickers, legal suffixes, bylines, keyword frequency).",
        sources=[source.id],
        fallback_reason=meta if isinstance(meta, str) else None,
    )


def suggest_topics(session: Session, source: Source, provider: LLMProvider | None) -> OperationOutput:
    prompt = (
        "Propose 3-8 short topic tags (1-3 words each) for this document. "
        'Reply as {"topics": ["...", "..."]}.\n\n'
        f"TITLE: {source.title}\n\nTEXT:\n{_context(source)}"
    )
    parsed, meta = _try_generate(
        session, provider, operation="suggest_topics", prompt=prompt,
        target_type="source", target_id=source.id,
    )
    if parsed is not None and isinstance(meta, Generation):
        topics = parsed.get("topics", []) if isinstance(parsed, dict) else parsed
        return OperationOutput(
            operation="suggest_topics",
            method="generated",
            provider=meta.provider,
            model=meta.model,
            items=[{"name": str(t).strip()} for t in topics if str(t).strip()][:12],
            notice="Model-suggested tags. Nothing is applied until you accept them.",
            generation_id=meta.id,
            sources=[source.id],
        )
    return OperationOutput(
        operation="suggest_topics",
        method="deterministic",
        provider="forge",
        model=None,
        items=[{"name": word, "count": count} for word, count in top_keywords(source.text or "", limit=10)],
        notice="Highest-frequency content words, stopwords removed.",
        sources=[source.id],
        fallback_reason=meta if isinstance(meta, str) else None,
    )


def extract_claims(session: Session, source: Source, provider: LLMProvider | None) -> OperationOutput:
    prompt = (
        "Extract the factual or forecasting claims made in the text. For each claim give the "
        "verbatim sentence it came from. "
        'Reply as {"claims": [{"claim": "...", "quote": "...", "stance": "bull|bear|risk|neutral"}]}.\n\n'
        f"TEXT:\n{_context(source)}"
    )
    parsed, meta = _try_generate(
        session, provider, operation="extract_claims", prompt=prompt,
        target_type="source", target_id=source.id,
    )
    if parsed is not None and isinstance(meta, Generation):
        raw = parsed.get("claims", []) if isinstance(parsed, dict) else parsed
        items = []
        for entry in raw if isinstance(raw, list) else []:
            if not isinstance(entry, dict) or not entry.get("claim"):
                continue
            quote = str(entry.get("quote", "")).strip()
            offset = (source.text or "").find(quote[:80]) if quote else -1
            stance = str(entry.get("stance", "neutral")).lower()
            items.append(
                {
                    "text": str(entry["claim"]).strip(),
                    "quote": quote,
                    "stance": stance if stance in {"bull", "bear", "risk", "neutral", "question"} else "neutral",
                    "char_start": offset if offset >= 0 else None,
                    "char_end": offset + len(quote) if offset >= 0 and quote else None,
                    "grounded": offset >= 0,
                }
            )
        return OperationOutput(
            operation="extract_claims",
            method="generated",
            provider=meta.provider,
            model=meta.model,
            items=items,
            notice="Model-extracted claims. Ungrounded claims could not be matched to the text.",
            generation_id=meta.id,
            sources=[source.id],
        )

    items = []
    text = source.text or ""
    for sentence in split_sentences(text):
        if len(sentence) < 60 or not CLAIM_MARKERS.search(sentence):
            continue
        offset = text.find(sentence)
        items.append(
            {
                "text": sentence.strip(),
                "quote": sentence.strip(),
                "stance": "neutral",
                "char_start": offset if offset >= 0 else None,
                "char_end": offset + len(sentence) if offset >= 0 else None,
                "grounded": True,
            }
        )
        if len(items) >= 12:
            break
    return OperationOutput(
        operation="extract_claims",
        method="deterministic",
        provider="forge",
        model=None,
        items=items,
        notice="Sentences containing claim-like language, copied verbatim. Not an interpretation.",
        sources=[source.id],
        fallback_reason=meta if isinstance(meta, str) else None,
    )


def generate_questions(session: Session, dossier: Dossier, provider: LLMProvider | None) -> OperationOutput:
    context_parts = [
        f"TITLE: {dossier.title}",
        f"OVERVIEW: {dossier.overview}",
        f"THESIS: {dossier.thesis}",
        f"BULL: {dossier.bull_case}",
        f"BEAR: {dossier.bear_case}",
        f"RISKS: {dossier.risks}",
        "CLAIMS:\n" + "\n".join(f"- [{c.stance}] {c.text}" for c in dossier.claims),
    ]
    prompt = (
        "Based only on this research dossier, list the open questions a careful analyst would "
        'still need to answer. Reply as {"questions": ["...", "..."]}.\n\n' + "\n\n".join(context_parts)
    )
    parsed, meta = _try_generate(
        session, provider, operation="generate_questions", prompt=prompt,
        target_type="dossier", target_id=dossier.id,
    )
    if parsed is not None and isinstance(meta, Generation):
        questions = parsed.get("questions", []) if isinstance(parsed, dict) else parsed
        return OperationOutput(
            operation="generate_questions",
            method="generated",
            provider=meta.provider,
            model=meta.model,
            items=[{"text": str(q).strip()} for q in questions if str(q).strip()][:15],
            notice="Model-generated questions. Treat as prompts for your own work, not findings.",
            generation_id=meta.id,
        )

    gaps: list[dict[str, Any]] = []
    unsupported = [c for c in dossier.claims if not c.evidence]
    for claim in unsupported[:6]:
        gaps.append({"text": f"What evidence supports the claim: “{claim.text}”?", "reason": "claim without evidence"})
    if not dossier.bear_case.strip():
        gaps.append({"text": "What is the strongest argument against this thesis?", "reason": "empty bear case"})
    if not dossier.risks.strip():
        gaps.append({"text": "Which risks would invalidate this dossier?", "reason": "empty risks section"})
    if not dossier.events:
        gaps.append({"text": "What are the dated events that shaped this subject?", "reason": "empty timeline"})
    if not any(item.target_type == "source" for item in dossier.items):
        gaps.append({"text": "Which primary sources back this dossier?", "reason": "no linked sources"})
    return OperationOutput(
        operation="generate_questions",
        method="deterministic",
        provider="forge",
        model=None,
        items=gaps,
        notice="Structural gaps found in this dossier. Deterministic, not an inference.",
        fallback_reason=meta if isinstance(meta, str) else None,
    )


def draft_comparison(
    session: Session,
    *,
    title: str,
    subjects: list[dict[str, Any]],
    dimensions: list[str],
    provider: LLMProvider | None,
) -> OperationOutput:
    body = "\n\n".join(
        f"SUBJECT {index + 1}: {subject['label']}\n{subject.get('context', '')[:4000]}"
        for index, subject in enumerate(subjects)
    )
    prompt = (
        f"Compare the following subjects across these dimensions: {', '.join(dimensions)}. "
        "Use only the supplied context; write 'not stated' when the context does not cover a cell. "
        'Reply as {"cells": [{"subject": "...", "dimension": "...", "value": "..."}]}.\n\n'
        f"TITLE: {title}\n\n{body}"
    )
    parsed, meta = _try_generate(
        session, provider, operation="draft_comparison", prompt=prompt,
        target_type="comparison", target_id=None,
    )
    if parsed is not None and isinstance(meta, Generation):
        raw = parsed.get("cells", []) if isinstance(parsed, dict) else parsed
        items = [
            {
                "subject": str(cell.get("subject", "")),
                "dimension": str(cell.get("dimension", "")),
                "value": str(cell.get("value", "")),
            }
            for cell in (raw if isinstance(raw, list) else [])
            if isinstance(cell, dict)
        ]
        return OperationOutput(
            operation="draft_comparison",
            method="generated",
            provider=meta.provider,
            model=meta.model,
            items=items,
            notice="Model-drafted cells. Every cell stays editable and is marked as generated.",
            generation_id=meta.id,
        )

    items = [
        {
            "subject": subject["label"],
            "dimension": dimension,
            "value": "",
            "hint": "No local model available - fill this in manually.",
        }
        for subject in subjects
        for dimension in dimensions
    ]
    return OperationOutput(
        operation="draft_comparison",
        method="deterministic",
        provider="forge",
        model=None,
        items=items,
        notice="Empty grid prepared. Comparison drafting is the one operation with no useful "
               "deterministic equivalent, so the cells are left blank rather than guessed.",
        fallback_reason=meta if isinstance(meta, str) else None,
    )


def accept_generation(session: Session, generation_id: str) -> Generation | None:
    generation = session.get(Generation, generation_id)
    if generation is None:
        return None
    generation.accepted = True
    session.flush()
    return generation


OPERATIONS = {
    "summarize": "Summarise a source",
    "extract_entities": "Extract entities from a source",
    "suggest_topics": "Suggest topic tags",
    "extract_claims": "Extract claims with quotes",
    "generate_questions": "Generate open questions for a dossier",
    "draft_comparison": "Draft comparison cells",
}


def knowledge_from_generation(
    kind: str, title: str, body: str, generation: Generation | None
) -> KnowledgeObject:
    """Build (but do not persist) a knowledge object flagged as generated."""

    return KnowledgeObject(
        kind=kind,
        title=title,
        body=body,
        status="draft",
        origin="generated" if generation else "user",
        generated_by=f"{generation.provider}:{generation.model}" if generation else None,
        generation_id=generation.id if generation else None,
    )
