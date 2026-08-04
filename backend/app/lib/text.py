"""Deterministic text analysis.

Everything in this module runs without a model, a network call or an API key.
It is the floor that FORGE guarantees: optional local LLM features can improve
on these results but never replace them.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from collections import Counter

# --- normalization ---------------------------------------------------------

_WS_RUN = re.compile(r"[ \t ]+")
_NEWLINES = re.compile(r"\n{3,}")


def normalize_text(raw: str) -> str:
    """Canonical form used for storage, hashing, search and offsets."""

    if not raw:
        return ""
    text = raw.replace("﻿", "")
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RUN.sub(" ", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _NEWLINES.sub("\n\n", text)
    return text.strip("\n")


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text, flags=re.UNICODE))


def slugify(value: str, max_length: int = 80) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    return value[:max_length].strip("-") or "item"


def truncate(text: str, limit: int = 240) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


# --- language --------------------------------------------------------------

EN_STOPWORDS = {
    "the", "and", "of", "to", "in", "is", "that", "it", "for", "on", "with", "as", "was", "are",
    "this", "be", "by", "from", "at", "an", "or", "we", "you", "not", "have", "has", "but", "they",
    "their", "which", "will", "can", "there", "been", "more", "about", "than", "when", "what",
}
ES_STOPWORDS = {
    "el", "la", "los", "las", "de", "del", "y", "que", "en", "un", "una", "por", "con", "para",
    "es", "se", "no", "al", "lo", "como", "más", "pero", "sus", "le", "ya", "o", "este", "sí",
    "porque", "esta", "entre", "cuando", "muy", "sin", "sobre", "también", "me", "hasta", "hay",
    "donde", "quien", "desde", "todo", "nos", "durante", "todos", "uno", "les", "ni", "contra",
}
STOPWORDS = EN_STOPWORDS | ES_STOPWORDS | {
    "s", "t", "d", "ll", "re", "ve", "m", "http", "https", "www", "com",
}


def detect_language(text: str, sample: int = 4000) -> str | None:
    """Very small EN/ES detector. Returns ``None`` when the sample is too thin.

    A frequency comparison over closed-class words is enough to separate the two
    languages this system actually sees, and it costs nothing.
    """

    words = re.findall(r"[a-záéíóúñü']+", text[:sample].lower())
    if len(words) < 20:
        return None
    counts = Counter(words)
    en = sum(counts[w] for w in EN_STOPWORDS)
    es = sum(counts[w] for w in ES_STOPWORDS)
    if en == es == 0:
        return None
    return "en" if en >= es else "es"


# --- structure -------------------------------------------------------------

_SENTENCE_END = re.compile(r"(?<=[.!?…])[\s\n]+(?=[A-ZÁÉÍÓÚÑ¿¡\"'(\[])")


def split_sentences(text: str) -> list[str]:
    chunks = [c.strip() for c in _SENTENCE_END.split(text) if c.strip()]
    return chunks


def top_keywords(text: str, limit: int = 12, min_length: int = 4) -> list[tuple[str, int]]:
    words = [
        w.lower()
        for w in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñü][\w'-]{%d,}" % (min_length - 1), text)
    ]
    counts = Counter(w for w in words if w not in STOPWORDS and not w.isdigit())
    return counts.most_common(limit)


def extractive_summary(text: str, max_sentences: int = 3, max_chars: int = 700) -> str:
    """Lead-biased, keyword-scored extractive summary.

    Deterministic and clearly not a paraphrase: sentences are copied verbatim
    from the source, which keeps the summary quotable and traceable.
    """

    sentences = split_sentences(text)
    if not sentences:
        return ""
    keywords = {word for word, _ in top_keywords(text, limit=20)}
    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(sentences[:60]):
        words = {w.lower() for w in re.findall(r"[\w'-]+", sentence)}
        overlap = len(words & keywords)
        length_penalty = 0.0 if 40 <= len(sentence) <= 320 else -1.5
        position_bonus = max(0.0, 3.0 - index * 0.25)
        scored.append((overlap + position_bonus + length_penalty, index, sentence))
    scored.sort(key=lambda item: (-item[0], item[1]))
    chosen = sorted(scored[:max_sentences], key=lambda item: item[1])
    out: list[str] = []
    total = 0
    for _, _, sentence in chosen:
        if total + len(sentence) > max_chars and out:
            break
        out.append(sentence.strip())
        total += len(sentence)
    return " ".join(out)


def guess_title(text: str, fallback: str = "Untitled source") -> str:
    for line in text.split("\n"):
        stripped = line.strip().lstrip("#").strip()
        if len(stripped) < 3:
            continue
        if len(stripped) > 200:
            stripped = truncate(stripped, 160)
        return stripped
    return fallback


# --- entity candidates -----------------------------------------------------

TICKER_RE = re.compile(r"(?<![A-Za-z0-9])\$([A-Z]{1,5})(?:\.[A-Z]{1,2})?(?![A-Za-z0-9])")
BARE_TICKER_RE = re.compile(r"(?<![A-Za-z0-9$])([A-Z]{2,5})(?![A-Za-z0-9])")
COMPANY_SUFFIX_RE = re.compile(
    r"\b([A-ZÁÉÍÓÚÑ][\w&.\-]*(?:\s+[A-ZÁÉÍÓÚÑ][\w&.\-]*){0,3})\s+"
    r"(Inc\.?|Corp\.?|Corporation|Ltd\.?|LLC|PLC|S\.A\.|SA|AG|NV|Holdings|Technologies|Systems|Group)\b"
)
PERSON_RE = re.compile(
    r"\b(?:By|Autor|Author|Interview with|Entrevista con|Guest|Host|Presented by)\s*:?\s+"
    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ']+){1,2})"
)
SPEAKER_RE = re.compile(r"^([A-ZÁÉÍÓÚÑ][\w.'-]*(?:\s+[A-ZÁÉÍÓÚÑ][\w.'-]*){0,2}):\s", re.MULTILINE)

#: Uppercase words that look like tickers but are not. Kept deliberately small;
#: bare uppercase tokens are always reported as low-confidence candidates.
TICKER_BLOCKLIST = {
    "CEO", "CFO", "COO", "CTO", "USA", "USD", "EUR", "GDP", "CPI", "PPI", "FED", "ETF", "IPO",
    "AI", "API", "SEC", "FDA", "EPS", "PE", "ROE", "ROI", "YOY", "QOQ", "TTM", "EBIT", "FCF",
    "OK", "PDF", "CSV", "JSON", "HTML", "URL", "FAQ", "AND", "THE", "FOR", "NOT", "ALL", "NEW",
    "AM", "PM", "UTC", "EST", "PST", "Q1", "Q2", "Q3", "Q4", "SA", "IT", "IS", "IN", "ON", "TO",
    "BUY", "SELL", "HOLD", "RSI", "MACD", "EMA", "SMA", "ATR", "VWAP", "IPOS", "ESG", "TAM",
}

ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
LONG_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def find_tickers(text: str) -> list[tuple[str, int, str]]:
    """Return ``(symbol, occurrences, confidence)`` candidates.

    ``$TSLA`` is treated as high confidence; a bare uppercase token is low
    confidence and is only surfaced for user confirmation.
    """

    explicit = Counter(m.group(1) for m in TICKER_RE.finditer(text))
    bare = Counter(
        m.group(1)
        for m in BARE_TICKER_RE.finditer(text)
        if m.group(1) not in TICKER_BLOCKLIST and m.group(1) not in explicit
    )
    out = [(sym, count, "high") for sym, count in explicit.most_common(20)]
    out += [(sym, count, "low") for sym, count in bare.most_common(10) if count >= 2]
    return out


def find_companies(text: str) -> list[tuple[str, int]]:
    counts = Counter(
        f"{m.group(1)} {m.group(2)}".strip() for m in COMPANY_SUFFIX_RE.finditer(text)
    )
    return counts.most_common(15)


def find_people(text: str) -> list[tuple[str, int]]:
    counts = Counter(m.group(1).strip() for m in PERSON_RE.finditer(text))
    for match in SPEAKER_RE.finditer(text):
        name = match.group(1).strip().rstrip(":")
        if len(name) > 2 and name.upper() != name:
            counts[name] += 1
    return [(name, count) for name, count in counts.most_common(15) if len(name) > 3]


def find_dates(text: str, limit: int = 5) -> list[dt.date]:
    found: list[dt.date] = []
    for match in ISO_DATE_RE.finditer(text):
        try:
            found.append(dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
        except ValueError:
            continue
        if len(found) >= limit:
            return found
    for match in LONG_DATE_RE.finditer(text):
        month = MONTHS[match.group(1).lower()]
        try:
            found.append(dt.date(int(match.group(3)), month, int(match.group(2))))
        except ValueError:
            continue
        if len(found) >= limit:
            break
    return found
