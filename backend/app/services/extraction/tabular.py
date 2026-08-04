"""CSV/TSV and JSON extraction.

Tabular data is turned into readable text so it lands in the same full-text
index as everything else, while the row/record locator keeps every excerpt
traceable back to an exact row.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from ...lib.text import normalize_text, truncate
from .base import DocumentUnit, ExtractedMetadata, ExtractionError, ExtractionResult, assemble
from .plain import decode_bytes

ROWS_PER_UNIT = 25
MAX_ROWS = 20000
MAX_CELL = 500


def extract_csv(data: bytes | str, filename: str | None = None) -> ExtractionResult:
    raw, encoding = decode_bytes(data) if isinstance(data, bytes) else (data, "utf-8")
    raw = raw.replace("\r\n", "\n")
    sample = raw[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = "\t" if (filename or "").lower().endswith(".tsv") else ","

    reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
    try:
        rows = [row for _, row in zip(range(MAX_ROWS + 1), reader, strict=False)]
    except csv.Error as exc:
        raise ExtractionError(f"could not parse CSV: {exc}") from exc
    if not rows:
        raise ExtractionError("CSV file is empty")

    warnings: list[str] = []
    truncated = len(rows) > MAX_ROWS
    if truncated:
        rows = rows[:MAX_ROWS]
        warnings.append(f"Only the first {MAX_ROWS} rows were imported.")

    header = [h.strip() for h in rows[0]]
    looks_like_header = bool(header) and all(h and not h.replace(".", "", 1).lstrip("-").isdigit() for h in header)
    body = rows[1:] if looks_like_header else rows
    if not looks_like_header:
        header = [f"column_{i + 1}" for i in range(len(rows[0]))]
        warnings.append("No header row detected; columns were numbered.")

    units: list[DocumentUnit] = []
    for start in range(0, max(len(body), 1), ROWS_PER_UNIT):
        block = body[start : start + ROWS_PER_UNIT]
        lines: list[str] = []
        for offset, row in enumerate(block):
            row_number = start + offset + (2 if looks_like_header else 1)
            pairs = [
                f"{header[i] if i < len(header) else f'column_{i + 1}'}: {truncate(cell, MAX_CELL)}"
                for i, cell in enumerate(row)
                if cell.strip()
            ]
            if pairs:
                lines.append(f"Row {row_number} — " + "; ".join(pairs))
        if lines:
            units.append(
                DocumentUnit(
                    kind="row_group",
                    text="\n".join(lines),
                    title=f"Rows {start + 1}-{start + len(block)}",
                    locator={
                        "row_start": start + (2 if looks_like_header else 1),
                        "row_end": start + len(block) + (1 if looks_like_header else 0),
                        "columns": header,
                    },
                )
            )
    if not units:
        units = [DocumentUnit(kind="whole", text=normalize_text(raw), locator={})]

    metadata = ExtractedMetadata(title=filename or "Tabular data")
    metadata.extra.update(
        {
            "encoding": encoding,
            "delimiter": delimiter,
            "columns": header,
            "row_count": len(body),
            "truncated": truncated,
        }
    )
    return assemble(units, "csv", metadata, warnings)


def _flatten(value: Any, prefix: str = "", depth: int = 0) -> list[str]:
    if depth > 6:
        return [f"{prefix}: …"]
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            out.extend(_flatten(item, f"{prefix}.{key}" if prefix else str(key), depth + 1))
        return out
    if isinstance(value, list):
        out = []
        for index, item in enumerate(value[:50]):
            out.extend(_flatten(item, f"{prefix}[{index}]", depth + 1))
        if len(value) > 50:
            out.append(f"{prefix}: … {len(value) - 50} more items")
        return out
    return [f"{prefix}: {truncate(str(value), MAX_CELL)}" if prefix else truncate(str(value), MAX_CELL)]


def extract_json(data: bytes | str, filename: str | None = None) -> ExtractionResult:
    raw, encoding = decode_bytes(data) if isinstance(data, bytes) else (data, "utf-8")
    warnings: list[str] = []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        records = []
        for line_number, line in enumerate(raw.split("\n"), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ExtractionError(
                    f"not valid JSON or JSON Lines (line {line_number}: {exc.msg})"
                ) from exc
        if not records:
            raise ExtractionError("JSON file is empty")
        payload = records
        warnings.append("Parsed as JSON Lines.")

    units: list[DocumentUnit] = []
    if isinstance(payload, list):
        for index, item in enumerate(payload[:2000]):
            text = "\n".join(_flatten(item))
            units.append(
                DocumentUnit(
                    kind="record",
                    text=text,
                    title=f"Record {index + 1}",
                    locator={"index": index, "pointer": f"/{index}"},
                )
            )
        if len(payload) > 2000:
            warnings.append(f"Only the first 2000 of {len(payload)} records were imported.")
    elif isinstance(payload, dict):
        for key, value in payload.items():
            units.append(
                DocumentUnit(
                    kind="record",
                    text="\n".join(_flatten(value, str(key))),
                    title=str(key),
                    locator={"key": key, "pointer": f"/{key}"},
                )
            )
    else:
        units.append(DocumentUnit(kind="whole", text=str(payload), locator={}))

    metadata = ExtractedMetadata(title=filename or "JSON data")
    metadata.extra.update(
        {
            "encoding": encoding,
            "root_type": type(payload).__name__,
            "record_count": len(payload) if isinstance(payload, list | dict) else 1,
        }
    )
    return assemble(units, "json", metadata, warnings)
