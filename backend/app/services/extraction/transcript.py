"""Transcript extraction for YouTube / podcast text, WebVTT and SRT.

Timestamps are the locator that makes a transcript excerpt traceable, so the
parser is deliberately generous about the formats it recognises:

* ``WEBVTT`` and ``.srt`` cue blocks
* ``[00:12:34] text`` and ``00:12 text`` inline stamps (the YouTube copy format)
* a bare ``12:34`` line followed by the text on the next line
* ``Speaker: text`` turns, with or without a timestamp
"""

from __future__ import annotations

import re

from ...lib.text import normalize_text, truncate
from .base import DocumentUnit, ExtractedMetadata, ExtractionResult, assemble
from .plain import decode_bytes

CUE_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})\s*-->\s*(?P<end>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})"
)
INLINE_TS_RE = re.compile(r"^\s*[\[(]?(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)[\])]?\s*[-–—]?\s*(?P<text>.*)$")
BARE_TS_RE = re.compile(r"^\s*[\[(]?(\d{1,2}:\d{2}(?::\d{2})?)[\])]?\s*$")
#: A speaker label is 1-3 capitalised words with no digits, so a headline like
#: "Episode 41: Managing a position" is not mistaken for a speaker turn.
SPEAKER_RE = re.compile(
    r"^\s*(?P<speaker>[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ.'-]*"
    r"(?:\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ.'-]*){0,2}):\s+(?P<text>\S.*)$"
)
MAX_SEGMENT_CHARS = 1200


def parse_timestamp(value: str) -> int:
    parts = [p for p in re.split(r"[:]", value.replace(",", ".")) if p != ""]
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return int(seconds)


def format_timestamp(seconds: int) -> str:
    hours, rest = divmod(max(seconds, 0), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _is_cue_format(text: str) -> bool:
    return bool(CUE_RE.search(text[:4000]))


def _parse_cues(text: str) -> list[DocumentUnit]:
    units: list[DocumentUnit] = []
    blocks = re.split(r"\n\s*\n", text)
    for block in blocks:
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        cue = None
        body_lines: list[str] = []
        for line in lines:
            match = CUE_RE.search(line)
            if match and cue is None:
                cue = match
                continue
            if line.strip().isdigit() and cue is None and len(lines) > 1:
                continue
            if line.strip().upper().startswith("WEBVTT"):
                continue
            body_lines.append(line.strip())
        body = " ".join(body_lines).strip()
        if not body:
            continue
        if cue is None:
            units.append(DocumentUnit(kind="segment", text=body, locator={}))
            continue
        start = parse_timestamp(cue.group("start"))
        speaker = None
        speaker_match = SPEAKER_RE.match(body)
        if speaker_match:
            speaker = speaker_match.group("speaker").strip()
            body = speaker_match.group("text").strip()
        stamp = format_timestamp(start)
        units.append(
            DocumentUnit(
                kind="segment",
                text=f"[{stamp}] " + (f"{speaker}: " if speaker else "") + body,
                title=stamp,
                locator={
                    "timestamp_seconds": start,
                    "timestamp": stamp,
                    "end_seconds": parse_timestamp(cue.group("end")),
                    **({"speaker": speaker} if speaker else {}),
                },
            )
        )
    return _merge_short_segments(units)


def _parse_inline(text: str) -> list[DocumentUnit]:
    """One segment per timestamp.

    A line without its own timestamp is a continuation of the previous segment
    (pasted transcripts are usually hard-wrapped), so wrapping never fragments a
    speaker turn into locator-less pieces.
    """

    units: list[DocumentUnit] = []
    pending_ts: int | None = None
    for line in text.split("\n"):
        if not line.strip():
            continue
        bare = BARE_TS_RE.match(line)
        if bare:
            pending_ts = parse_timestamp(bare.group(1))
            continue

        body = line.strip()
        seconds: int | None = pending_ts
        pending_ts = None
        inline = INLINE_TS_RE.match(line)
        if inline and inline.group("text").strip():
            seconds = parse_timestamp(inline.group("ts"))
            body = inline.group("text").strip()

        if seconds is None and units:
            # Continuation of the previous turn.
            units[-1].text = f"{units[-1].text} {body}".strip()
            continue

        speaker = None
        speaker_match = SPEAKER_RE.match(body)
        if speaker_match:
            speaker = speaker_match.group("speaker").strip()
            body = speaker_match.group("text").strip()
        if not body:
            continue

        stamp = format_timestamp(seconds) if seconds is not None else None
        prefix = f"[{stamp}] " if stamp else ""
        prefix += f"{speaker}: " if speaker else ""
        locator: dict[str, object] = {}
        if seconds is not None:
            locator.update({"timestamp_seconds": seconds, "timestamp": stamp})
        if speaker:
            locator["speaker"] = speaker
        units.append(DocumentUnit(kind="segment", text=prefix + body, title=stamp, locator=locator))
    return units


def _merge_short_segments(units: list[DocumentUnit]) -> list[DocumentUnit]:
    """Merge consecutive cues into readable paragraphs, keeping the first stamp."""

    merged: list[DocumentUnit] = []
    for unit in units:
        if merged and len(merged[-1].text) + len(unit.text) < MAX_SEGMENT_CHARS:
            previous = merged[-1]
            previous.text = f"{previous.text} {unit.text}".strip()
            end = unit.locator.get("end_seconds") or unit.locator.get("timestamp_seconds")
            if end is not None:
                previous.locator["end_seconds"] = end
            continue
        merged.append(unit)
    return merged


def _guess_transcript_title(text: str, filename: str | None) -> str:
    """First meaningful line, with any timestamp and speaker label removed.

    A pasted transcript usually starts with ``0:00 Host: …``; carrying that
    prefix into the title makes every transcript in the library look the same.
    """

    for line in text.split("\n"):
        candidate = line.strip()
        if len(candidate) < 3:
            continue
        inline = INLINE_TS_RE.match(candidate)
        if inline and inline.group("text").strip():
            candidate = inline.group("text").strip()
        elif BARE_TS_RE.match(candidate):
            continue
        speaker = SPEAKER_RE.match(candidate)
        if speaker:
            candidate = speaker.group("text").strip()
        if len(candidate) < 3:
            continue
        return truncate(candidate, 160)
    return filename or "Transcript"


def extract_transcript(data: bytes | str, filename: str | None = None) -> ExtractionResult:
    raw, encoding = decode_bytes(data) if isinstance(data, bytes) else (data, "utf-8")
    text = normalize_text(raw)
    warnings: list[str] = []

    if _is_cue_format(text):
        units = _parse_cues(text)
        method = "transcript_cues"
    else:
        units = _parse_inline(text)
        method = "transcript_inline"

    stamped = sum(1 for u in units if "timestamp_seconds" in u.locator)
    if not stamped:
        warnings.append(
            "No timestamps were detected; excerpts from this transcript will be located by "
            "paragraph instead of by time."
        )
    speakers = sorted({str(u.locator["speaker"]) for u in units if u.locator.get("speaker")})

    metadata = ExtractedMetadata(title=_guess_transcript_title(text, filename))
    metadata.extra.update(
        {
            "encoding": encoding,
            "segment_count": len(units),
            "timestamped_segments": stamped,
            "speakers": speakers,
            "duration_seconds": max(
                (int(u.locator.get("end_seconds") or u.locator.get("timestamp_seconds") or 0) for u in units),
                default=0,
            ),
        }
    )
    return assemble(units, method, metadata, warnings)
