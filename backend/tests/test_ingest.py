"""Import pipeline: duplicates, rejections, failure handling, provenance."""

from __future__ import annotations

import pytest
from app.domain import SourceKind, SourceStatus
from app.lib.hashing import sha256_bytes
from app.models import Document, Source
from app.services import ingest, storage
from app.services.ingest import ImportRejected


class TestFileImport:
    def test_pdf_import_stores_original_text_and_documents(self, session, sample_bytes) -> None:  # noqa: ANN001
        data = sample_bytes("helios-q3-fy2026-review.pdf")
        outcome = ingest.ingest_bytes(session, data=data, filename="helios.pdf")

        assert outcome.ok
        source = outcome.source
        assert source.kind == SourceKind.PDF
        assert source.status == SourceStatus.NEEDS_REVIEW
        assert source.content_hash == sha256_bytes(data)
        assert source.char_count > 1000
        assert source.word_count > 200
        assert source.page_count == len(source.documents) >= 2
        assert storage.blob_exists(source.storage_path)
        assert storage.read_blob(source.storage_path) == data

    def test_document_offsets_point_into_source_text(self, session, sample_bytes) -> None:  # noqa: ANN001
        outcome = ingest.ingest_bytes(
            session, data=sample_bytes("helios-q3-fy2026-review.pdf"), filename="helios.pdf"
        )
        source = outcome.source
        for document in source.documents:
            assert source.text[document.char_start : document.char_end] == document.text

    def test_detected_metadata_is_populated(self, session, sample_bytes) -> None:  # noqa: ANN001
        outcome = ingest.ingest_bytes(
            session, data=sample_bytes("helios-q3-fy2026-review.pdf"), filename="helios.pdf"
        )
        detected = outcome.source.detected_metadata
        assert detected["language"] == "en"
        assert detected["keywords"]
        assert isinstance(detected["entity_candidates"], list)
        assert outcome.source.summary

    def test_kind_is_inferred_from_extension(self, session) -> None:  # noqa: ANN001
        outcome = ingest.ingest_bytes(session, data=b"# Title\n\nBody text here.", filename="note.md")
        assert outcome.source.kind == SourceKind.MARKDOWN

    def test_transcript_is_detected_inside_a_txt_file(self, session, sample_bytes) -> None:  # noqa: ANN001
        outcome = ingest.ingest_bytes(
            session, data=sample_bytes("momentum-masterclass-ep41.txt"), filename="ep41.txt"
        )
        assert outcome.source.kind == SourceKind.TRANSCRIPT
        assert any("timestamp_seconds" in d.locator for d in outcome.source.documents)


class TestDuplicateDetection:
    def test_identical_bytes_are_reported_as_duplicates(self, session, sample_bytes) -> None:  # noqa: ANN001
        data = sample_bytes("helios-q3-fy2026-review.pdf")
        first = ingest.ingest_bytes(session, data=data, filename="helios.pdf")
        second = ingest.ingest_bytes(session, data=data, filename="helios-copy.pdf")

        assert first.ok
        assert second.status == "duplicate"
        assert second.duplicate_of.id == first.source.id
        assert session.query(Source).count() == 1

    def test_force_imports_a_duplicate_anyway(self, session, sample_bytes) -> None:  # noqa: ANN001
        data = sample_bytes("helios-q3-fy2026-review.pdf")
        ingest.ingest_bytes(session, data=data, filename="helios.pdf")
        forced = ingest.ingest_bytes(session, data=data, filename="helios.pdf", force=True)

        assert forced.ok
        assert session.query(Source).count() == 2

    def test_near_identical_pasted_text_is_detected(self, session) -> None:  # noqa: ANN001
        text = "The margin expansion was driven by mix and not by pricing power this quarter."
        first = ingest.ingest_text(session, text=text)
        rewrapped = ingest.ingest_text(session, text="The margin expansion was driven by mix\nand not by pricing power this   quarter.")

        assert first.ok
        assert rewrapped.status == "duplicate"
        assert "Near-identical" in rewrapped.message

    def test_different_text_is_not_a_duplicate(self, session) -> None:  # noqa: ANN001
        ingest.ingest_text(session, text="First note about power constraints in data centres.")
        second = ingest.ingest_text(session, text="Second note about networking attach rates.")
        assert second.ok

    def test_duplicate_blob_is_stored_once(self, session, sample_bytes) -> None:  # noqa: ANN001
        data = sample_bytes("hlsx-daily-chart.png")
        first = ingest.ingest_bytes(session, data=data, filename="chart.png")
        second = ingest.ingest_bytes(session, data=data, filename="chart2.png", force=True)
        assert first.source.storage_path == second.source.storage_path


class TestRejections:
    def test_empty_file_is_rejected(self, session) -> None:  # noqa: ANN001
        with pytest.raises(ImportRejected):
            ingest.ingest_bytes(session, data=b"", filename="empty.txt")

    def test_oversized_file_is_rejected(self, session, monkeypatch) -> None:  # noqa: ANN001
        from app.config import get_settings, reset_settings_cache

        monkeypatch.setenv("FORGE_MAX_UPLOAD_MB", "0")
        reset_settings_cache()
        with pytest.raises(ImportRejected, match="over the"):
            ingest.ingest_bytes(session, data=b"x" * 2048, filename="big.txt", settings=get_settings())
        reset_settings_cache()

    def test_pdf_signature_is_verified(self, session) -> None:  # noqa: ANN001
        with pytest.raises(ImportRejected, match="%PDF-"):
            ingest.ingest_bytes(session, data=b"not a pdf at all", filename="fake.pdf", kind="pdf")

    def test_image_signature_is_verified(self, session) -> None:  # noqa: ANN001
        with pytest.raises(ImportRejected, match="image"):
            ingest.ingest_bytes(session, data=b"still not an image", filename="fake.png", kind="image")

    def test_empty_paste_is_rejected(self, session) -> None:  # noqa: ANN001
        with pytest.raises(ImportRejected):
            ingest.ingest_text(session, text="   \n  ")

    def test_binary_kinds_cannot_be_pasted(self, session) -> None:  # noqa: ANN001
        with pytest.raises(ImportRejected, match="uploaded as a file"):
            ingest.ingest_text(session, text="hello", kind="pdf")


class TestFailureHandling:
    def test_unparseable_file_becomes_an_error_source_not_a_lost_file(self, session) -> None:  # noqa: ANN001
        data = b"%PDF-1.4\ncompletely broken internals"
        outcome = ingest.ingest_bytes(session, data=data, filename="broken.pdf")

        assert outcome.status == "error"
        source = outcome.source
        assert source.status == SourceStatus.ERROR
        assert source.error_message
        assert storage.blob_exists(source.storage_path), "the original bytes must survive a parse failure"

    def test_scanned_pdf_warning_is_surfaced(self, session) -> None:  # noqa: ANN001
        from helpers import blank_pdf

        outcome = ingest.ingest_bytes(session, data=blank_pdf(), filename="scan.pdf")
        assert outcome.ok
        assert any("scanned" in warning.lower() for warning in outcome.source.extraction_warnings)


class TestReprocess:
    def test_reprocess_rebuilds_documents(self, session, sample_bytes) -> None:  # noqa: ANN001
        outcome = ingest.ingest_bytes(
            session, data=sample_bytes("market-breadth-2026.csv"), filename="breadth.csv"
        )
        source = outcome.source
        before = session.query(Document).filter(Document.source_id == source.id).count()
        ingest.mark_reviewed(session, source)

        again = ingest.reprocess(session, source)
        after = session.query(Document).filter(Document.source_id == source.id).count()

        assert again.status == "created"
        assert before == after
        assert source.status == SourceStatus.NEEDS_REVIEW


class TestReview:
    def test_marking_reviewed_attaches_entities(self, session, sample_bytes) -> None:  # noqa: ANN001
        outcome = ingest.ingest_bytes(
            session, data=sample_bytes("helios-q3-fy2026-review.pdf"), filename="helios.pdf"
        )
        source = outcome.source
        ingest.mark_reviewed(
            session,
            source,
            confirmed_entities=[{"kind": "ticker", "name": "HLSX", "detector": "user"}],
        )
        from app.services.entities import entities_for_source

        assert source.status == SourceStatus.READY
        assert source.reviewed_at is not None
        assert [e.name for e in entities_for_source(session, source.id)] == ["HLSX"]
