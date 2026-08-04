"""Unit tests for the pure helpers."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from app.lib.files import (
    detect_magic,
    extension_of,
    resolve_within,
    sanitize_filename,
    sniff_mime,
    storage_relative_path,
)
from app.lib.hashing import sha256_bytes, sha256_text
from app.lib.provenance import citation, locator_label
from app.lib.text import (
    detect_language,
    extractive_summary,
    find_dates,
    find_tickers,
    normalize_text,
    slugify,
    split_sentences,
    top_keywords,
    word_count,
)
from app.types import DecimalText, IsoDate, UtcDateTime


class TestNormalization:
    def test_collapses_whitespace_and_newlines(self) -> None:
        assert normalize_text("a  \t b\r\nc\r\n\n\n\nd  ") == "a b\nc\n\nd"

    def test_strips_bom_and_normalizes_unicode(self) -> None:
        assert normalize_text("\ufeffcafe\u0301") == "café"

    def test_empty_input(self) -> None:
        assert normalize_text("") == ""

    def test_word_count_handles_punctuation(self) -> None:
        # "It's", "a", "well-known", "two-part", "rule"
        assert word_count("It's a well-known, two-part rule.") == 5


class TestSlug:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Helios Semiconductor (HLSX)", "helios-semiconductor-hlsx"),
            ("  Múltiple   Espacios ", "multiple-espacios"),
            ("///", "item"),
        ],
    )
    def test_slugify(self, value: str, expected: str) -> None:
        assert slugify(value) == expected


class TestLanguage:
    def test_detects_english(self) -> None:
        text = "The company said that the margin expansion was driven by mix and not by pricing " * 3
        assert detect_language(text) == "en"

    def test_detects_spanish(self) -> None:
        text = "La empresa dijo que la expansión del margen se debe a la mezcla y no al precio " * 3
        assert detect_language(text) == "es"

    def test_returns_none_for_short_text(self) -> None:
        assert detect_language("too short") is None


class TestExtraction:
    def test_summary_uses_verbatim_sentences(self) -> None:
        text = (
            "Revenue grew 41% year over year. The margin expansion was driven by mix. "
            "Management guided to a deceleration next quarter. Inventory rose sharply."
        )
        summary = extractive_summary(text, max_sentences=2)
        assert summary
        for sentence in split_sentences(summary):
            assert sentence in text

    def test_keywords_exclude_stopwords(self) -> None:
        words = dict(top_keywords("margin margin margin the the the there there there"))
        assert "margin" in words
        assert "the" not in words and "there" not in words

    def test_finds_explicit_tickers_with_high_confidence(self) -> None:
        found = dict((symbol, confidence) for symbol, _, confidence in find_tickers("Long $HLSX and $VLTR here"))
        assert found["HLSX"] == "high"

    def test_blocklists_common_uppercase_words(self) -> None:
        symbols = [symbol for symbol, _, _ in find_tickers("The CEO said the USA GDP and the CPI. CEO CPI GDP")]
        assert "CEO" not in symbols and "GDP" not in symbols

    def test_finds_dates(self) -> None:
        assert dt.date(2026, 7, 24) in find_dates("Reported on 2026-07-24 after the close")
        assert dt.date(2026, 3, 5) in find_dates("Published March 5, 2026 in the letter")


class TestHashing:
    def test_text_hash_ignores_whitespace_and_case(self) -> None:
        assert sha256_text("Hello   world\n") == sha256_text("hello world")

    def test_byte_hash_is_exact(self) -> None:
        assert sha256_bytes(b"a") != sha256_bytes(b"A")


class TestFileSafety:
    @pytest.mark.parametrize(
        "name",
        ["../../etc/passwd", "..\\..\\windows\\system32\\cmd.exe", "C:\\abs\\path.txt"],
    )
    def test_sanitize_strips_directories(self, name: str) -> None:
        cleaned = sanitize_filename(name)
        assert "/" not in cleaned and "\\" not in cleaned and ".." not in cleaned

    def test_windows_reserved_names_are_prefixed(self) -> None:
        assert sanitize_filename("CON.txt").startswith("_")

    def test_empty_name_falls_back(self) -> None:
        assert sanitize_filename("   ") == "upload"

    def test_extension_detection(self) -> None:
        assert extension_of("Report.FINAL.PDF") == ".pdf"

    def test_storage_path_rejects_weird_extensions(self) -> None:
        assert storage_relative_path("a" * 64, "../evil").endswith("a" * 64)

    def test_resolve_within_blocks_escape(self, tmp_path) -> None:  # noqa: ANN001
        with pytest.raises(ValueError):
            resolve_within(tmp_path, "../outside.txt")

    def test_sniff_detects_pdf_and_png(self) -> None:
        assert sniff_mime(b"%PDF-1.4 rest") == "application/pdf"
        assert sniff_mime(b"\x89PNG\r\n\x1a\n") == "image/png"
        assert sniff_mime(b"plain", ".txt") == "text/plain"

    def test_magic_detection_ignores_the_extension(self) -> None:
        assert detect_magic(b"plain text pretending to be a png") is None
        assert detect_magic(b"%PDF-1.7") == "application/pdf"


class TestProvenance:
    @pytest.mark.parametrize(
        ("locator", "expected"),
        [
            ({"page": 4}, "p. 4"),
            ({"timestamp": "12:30"}, "[12:30]"),
            ({"row_start": 26, "row_end": 50}, "rows 26-50"),
            ({"section": "Risks"}, "§ Risks"),
            ({"pointer": "/positions"}, "/positions"),
            ({}, ""),
        ],
    )
    def test_locator_labels(self, locator: dict, expected: str) -> None:
        assert locator_label(locator) == expected

    def test_citation_includes_every_known_part(self) -> None:
        text = citation(
            "Q3 Review", author="Desk", published_on="2026-07-24",
            locator={"page": 2}, url="https://example.invalid/x",
        )
        assert "Q3 Review" in text and "Desk" in text and "p. 2" in text and "example.invalid" in text


class TestColumnTypes:
    def test_utc_datetime_roundtrip_is_timezone_aware(self) -> None:
        column = UtcDateTime()
        stored = column.process_bind_param(dt.datetime(2026, 1, 2, 3, 4, 5), None)
        loaded = column.process_result_value(stored, None)
        assert loaded.tzinfo is not None
        assert loaded == dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC)

    def test_decimal_text_is_exact(self) -> None:
        column = DecimalText()
        stored = column.process_bind_param(Decimal("0.1"), None)
        assert stored == "0.1"
        assert column.process_result_value(stored, None) + Decimal("0.2") == Decimal("0.3")

    def test_iso_date_roundtrip(self) -> None:
        column = IsoDate()
        assert column.process_result_value(column.process_bind_param(dt.date(2026, 7, 24), None), None) == dt.date(2026, 7, 24)
