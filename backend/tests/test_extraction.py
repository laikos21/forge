"""Extraction tests, including the edge cases that decide whether an import
lands as a usable source or as a clearly-reported failure."""

from __future__ import annotations

import json

import pytest
from app.services.extraction import ExtractionError, extract, kind_for_filename, looks_like_transcript
from app.services.extraction.base import UNIT_SEPARATOR
from app.services.extraction.transcript import format_timestamp, parse_timestamp


def assert_offsets_match_text(result) -> None:  # noqa: ANN001
    """The contract every extractor must honour."""

    for unit in result.units:
        assert result.text[unit.char_start : unit.char_end] == unit.text
    if len(result.units) > 1:
        joined = UNIT_SEPARATOR.join(u.text for u in result.units)
        assert joined == result.text


class TestPdf:
    def test_extracts_pages_metadata_and_offsets(self, sample_bytes) -> None:  # noqa: ANN001
        result = extract("pdf", sample_bytes("helios-q3-fy2026-review.pdf"), "helios.pdf")
        assert result.method == "pypdf"
        assert result.metadata.page_count == len(result.units) >= 2
        assert result.metadata.author == "Demo Research Desk"
        assert result.metadata.published_on is not None
        assert all(u.locator["page"] == i + 1 for i, u in enumerate(result.units))
        assert "Gross margin" in result.text
        assert_offsets_match_text(result)

    def test_corrupt_pdf_raises_extraction_error(self) -> None:
        with pytest.raises(ExtractionError):
            extract("pdf", b"%PDF-1.4\nthis is not really a pdf", "broken.pdf")

    def test_pdf_requires_bytes(self) -> None:
        with pytest.raises(ExtractionError):
            extract("pdf", "text instead of bytes", "x.pdf")


class TestPlainAndMarkdown:
    def test_markdown_sections_and_front_matter(self, sample_bytes) -> None:  # noqa: ANN001
        result = extract("markdown", sample_bytes("swing-trading-rules.md"), "rules.md")
        titles = [u.title for u in result.units]
        assert "1. Environment before setup" in titles
        assert result.metadata.author == "Demo User"
        assert result.metadata.extra["tags"] == ["rules", "risk", "process"]
        assert all(u.kind == "section" for u in result.units)
        assert_offsets_match_text(result)

    def test_markdown_without_headings_still_produces_units(self) -> None:
        result = extract("markdown", "just one paragraph of text", "note.md")
        assert len(result.units) == 1
        assert result.text == "just one paragraph of text"

    def test_plain_text_chunks_large_input(self) -> None:
        text = "\n\n".join("paragraph " + "x" * 500 for _ in range(30))
        result = extract("text", text, "big.txt")
        assert len(result.units) > 1
        assert_offsets_match_text(result)

    def test_html_is_stripped_for_web_articles(self) -> None:
        html = "<html><head><title>Power grid</title></head><body><p>First para.</p><script>bad()</script><p>Second.</p></body></html>"
        result = extract("web_article", html, None)
        assert "bad()" not in result.text
        assert "First para." in result.text and "Second." in result.text
        assert result.metadata.title == "Power grid"
        assert result.warnings

    def test_latin1_bytes_decode_without_crashing(self) -> None:
        result = extract("text", "café presión".encode("cp1252"), "legacy.txt")
        assert "caf" in result.text


class TestTranscript:
    def test_inline_timestamps_become_segment_locators(self, sample_bytes) -> None:  # noqa: ANN001
        result = extract("transcript", sample_bytes("momentum-masterclass-ep41.txt"), "ep41.txt")
        stamped = [u for u in result.units if "timestamp_seconds" in u.locator]
        assert len(stamped) >= 10
        assert result.metadata.extra["speakers"] == ["Dana Ruiz", "Host"]
        assert_offsets_match_text(result)

    def test_webvtt_cues(self) -> None:
        vtt = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:04.000\nFirst cue text\n\n"
            "00:01:05.000 --> 00:01:09.000\nSecond cue text\n"
        )
        result = extract("transcript", vtt, "clip.vtt")
        assert result.method == "transcript_cues"
        assert result.units[0].locator["timestamp_seconds"] == 1

    def test_wrapped_lines_join_the_previous_segment(self) -> None:
        text = "0:10 Host: A sentence that was hard\nwrapped by the exporter.\n0:20 Guest: Next turn."
        result = extract("transcript", text, "wrapped.txt")
        assert len(result.units) == 2
        assert "hard wrapped by the exporter." in result.units[0].text

    def test_title_drops_the_leading_timestamp_and_speaker(self) -> None:
        result = extract("transcript", "0:00 Host: Managing risk after entry.\n0:20 Guest: Agreed.", "clip.txt")
        assert result.metadata.title == "Managing risk after entry."

    def test_title_prefers_a_real_heading_when_present(self, sample_bytes) -> None:  # noqa: ANN001
        result = extract("transcript", sample_bytes("momentum-masterclass-ep41.txt"), "ep41.txt")
        assert result.metadata.title.startswith("Momentum Masterclass")

    def test_transcript_without_timestamps_warns(self) -> None:
        result = extract("transcript", "Just some prose\nwith no timestamps at all.", "notimes.txt")
        assert any("No timestamps" in w for w in result.warnings)

    @pytest.mark.parametrize(("value", "seconds"), [("1:30", 90), ("01:00:00", 3600), ("00:00:04.500", 4)])
    def test_timestamp_parsing(self, value: str, seconds: int) -> None:
        assert parse_timestamp(value) == seconds

    def test_timestamp_formatting(self) -> None:
        assert format_timestamp(90) == "1:30"
        assert format_timestamp(3661) == "1:01:01"

    def test_detection_heuristic(self, sample_bytes) -> None:  # noqa: ANN001
        assert looks_like_transcript(sample_bytes("momentum-masterclass-ep41.txt").decode())
        assert not looks_like_transcript("A normal paragraph of prose without any timing marks at all.")

    def test_short_fully_stamped_paste_is_a_transcript(self) -> None:
        assert looks_like_transcript("0:15 Host: One line.\n1:02 Guest: Another line.")

    def test_a_single_stamped_line_is_not_enough(self) -> None:
        assert not looks_like_transcript("0:15 Host: One line only.")


class TestTabular:
    def test_csv_header_detection_and_row_locators(self, sample_bytes) -> None:  # noqa: ANN001
        result = extract("csv", sample_bytes("market-breadth-2026.csv"), "breadth.csv")
        assert result.metadata.extra["columns"][0] == "date"
        assert result.metadata.extra["row_count"] == 9
        assert result.units[0].locator["row_start"] == 2
        assert "pct_above_50dma" in result.text

    def test_csv_without_header_is_flagged(self) -> None:
        result = extract("csv", "1,2,3\n4,5,6\n", "numbers.csv")
        assert any("No header row" in w for w in result.warnings)
        assert result.metadata.extra["columns"] == ["column_1", "column_2", "column_3"]

    def test_semicolon_delimiter_is_sniffed(self) -> None:
        result = extract("csv", "name;value\nalpha;1\nbeta;2\n", "euro.csv")
        assert result.metadata.extra["delimiter"] == ";"
        assert result.metadata.extra["row_count"] == 2

    def test_empty_csv_raises(self) -> None:
        with pytest.raises(ExtractionError):
            extract("csv", "", "empty.csv")

    def test_json_records(self, sample_bytes) -> None:  # noqa: ANN001
        result = extract("json", sample_bytes("positions-snapshot.json"), "positions.json")
        assert result.metadata.extra["root_type"] == "dict"
        assert any(u.title == "positions" for u in result.units)
        assert "HLSX" in result.text

    def test_json_lines_fallback(self) -> None:
        result = extract("json", '{"a": 1}\n{"a": 2}\n', "stream.jsonl")
        assert "Parsed as JSON Lines." in result.warnings
        assert len(result.units) == 2

    def test_invalid_json_raises_with_line_number(self) -> None:
        with pytest.raises(ExtractionError) as error:
            extract("json", "{not json at all}", "bad.json")
        assert "line 1" in str(error.value)

    def test_json_array_produces_indexed_pointers(self) -> None:
        result = extract("json", json.dumps([{"x": 1}, {"x": 2}]), "list.json")
        assert result.units[1].locator["pointer"] == "/1"


class TestImage:
    def test_metadata_only_extraction(self, sample_bytes) -> None:  # noqa: ANN001
        result = extract("image", sample_bytes("hlsx-daily-chart.png"), "chart.png")
        assert result.method == "image_metadata"
        assert result.metadata.extra["width"] == 900
        assert "900x480" in result.text
        assert any("No text layer" in w for w in result.warnings)

    def test_ocr_request_without_tesseract_degrades_gracefully(self, sample_bytes) -> None:  # noqa: ANN001
        result = extract("image", sample_bytes("hlsx-daily-chart.png"), "chart.png", ocr=True)
        assert result.units  # still a usable source
        assert result.metadata.extra["width"] == 900

    def test_corrupt_image_raises(self) -> None:
        with pytest.raises(ExtractionError):
            extract("image", b"\x89PNG\r\n\x1a\nnot really a png", "broken.png")


class TestRouting:
    @pytest.mark.parametrize(
        ("filename", "kind"),
        [("a.pdf", "pdf"), ("a.md", "markdown"), ("a.csv", "csv"), ("a.json", "json"),
         ("a.png", "image"), ("a.vtt", "transcript"), ("a.txt", "text")],
    )
    def test_kind_for_filename(self, filename: str, kind: str) -> None:
        assert kind_for_filename(filename) == kind

    def test_unknown_extension_returns_none(self) -> None:
        assert kind_for_filename("archive.zip") is None

    def test_unsupported_kind_raises(self) -> None:
        with pytest.raises(ValueError):
            extract("spreadsheet", b"x", "a.xlsx")
