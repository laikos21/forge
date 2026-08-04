"""User preferences held in the database (as opposed to deployment config).

Every key has a declared default and a type, so an unknown or malformed value in
the table can never crash a screen: it falls back to the default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AppSetting


@dataclass(frozen=True, slots=True)
class Preference:
    key: str
    default: Any
    type: str
    label: str
    help: str
    group: str
    choices: tuple[str, ...] = ()


PREFERENCES: tuple[Preference, ...] = (
    Preference("ui.theme", "dark", "choice", "Theme", "Dark is the default for long research sessions.", "Interface", ("dark", "light")),
    Preference("ui.density", "comfortable", "choice", "Density", "Row height in tables and lists.", "Interface", ("comfortable", "compact")),
    Preference("ui.default_library_view", "grid", "choice", "Default library view", "Grid or table when opening the Library.", "Interface", ("grid", "table")),
    Preference("import.auto_review", False, "bool", "Skip the review step", "Mark imports as ready immediately instead of routing them through Inbox review.", "Import"),
    Preference("import.ocr_images", False, "bool", "OCR images on import", "Requires Tesseract. Ignored when unavailable.", "Import"),
    Preference("import.ocr_language", "eng", "text", "OCR language", "Tesseract language code, e.g. eng or spa.", "Import"),
    Preference("llm.enabled", False, "bool", "Enable local LLM features", "Optional. FORGE is fully functional with this off.", "Local intelligence"),
    Preference("llm.provider", "ollama", "choice", "Provider", "Only local providers are supported.", "Local intelligence", ("ollama",)),
    Preference("llm.base_url", "http://127.0.0.1:11434", "text", "Provider base URL", "Ollama's local HTTP endpoint. Prefer 127.0.0.1 over localhost on Windows.", "Local intelligence"),
    Preference("llm.model", "llama3.1:8b", "text", "Model", "Any model already pulled in Ollama.", "Local intelligence"),
    Preference("semantic.enabled", False, "bool", "Enable semantic search", "Adds embedding-based results next to full-text results.", "Search"),
    Preference("semantic.model", "nomic-embed-text", "text", "Embedding model", "Ollama embedding model used to build the local vector index.", "Search"),
    Preference("search.default_ref_types", ["source", "excerpt", "knowledge", "dossier"], "list", "Searched object types", "Which object types the search box looks at by default.", "Search"),
)

BY_KEY = {pref.key: pref for pref in PREFERENCES}


def _coerce(pref: Preference, value: Any) -> Any:
    if pref.type == "bool":
        return bool(value)
    if pref.type == "choice":
        return value if value in pref.choices else pref.default
    if pref.type == "list":
        return [str(v) for v in value] if isinstance(value, list) else pref.default
    return str(value) if value is not None else pref.default


def get_all(session: Session) -> dict[str, Any]:
    stored = {row.key: row.value for row in session.execute(select(AppSetting)).scalars()}
    out: dict[str, Any] = {}
    for pref in PREFERENCES:
        raw = stored.get(pref.key)
        value = raw.get("value") if isinstance(raw, dict) and "value" in raw else raw
        out[pref.key] = pref.default if value is None else _coerce(pref, value)
    return out


def get(session: Session, key: str) -> Any:
    pref = BY_KEY.get(key)
    if pref is None:
        raise KeyError(key)
    row = session.get(AppSetting, key)
    if row is None or row.value is None:
        return pref.default
    raw = row.value.get("value") if isinstance(row.value, dict) and "value" in row.value else row.value
    return pref.default if raw is None else _coerce(pref, raw)


def set_many(session: Session, values: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(values) - set(BY_KEY))
    if unknown:
        raise KeyError(f"unknown preference(s): {', '.join(unknown)}")
    for key, value in values.items():
        pref = BY_KEY[key]
        coerced = _coerce(pref, value)
        row = session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value={"value": coerced}))
        else:
            row.value = {"value": coerced}
    session.flush()
    return get_all(session)


def reset(session: Session) -> dict[str, Any]:
    for row in session.execute(select(AppSetting)).scalars().all():
        session.delete(row)
    session.flush()
    return get_all(session)


def schema() -> list[dict[str, Any]]:
    return [
        {
            "key": p.key,
            "default": p.default,
            "type": p.type,
            "label": p.label,
            "help": p.help,
            "group": p.group,
            "choices": list(p.choices),
        }
        for p in PREFERENCES
    ]
