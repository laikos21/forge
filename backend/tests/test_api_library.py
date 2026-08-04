"""API integration tests for import, inbox, library and excerpts."""

from __future__ import annotations

from helpers import text_pdf, tiny_png


class TestImportEndpoints:
    def test_batch_upload_reports_each_file(self, client, sample_bytes) -> None:  # noqa: ANN001
        files = [
            ("files", ("helios.pdf", sample_bytes("helios-q3-fy2026-review.pdf"), "application/pdf")),
            ("files", ("rules.md", sample_bytes("swing-trading-rules.md"), "text/markdown")),
            ("files", ("breadth.csv", sample_bytes("market-breadth-2026.csv"), "text/csv")),
        ]
        response = client.post("/api/import/files", files=files, data={"batch_label": "Morning drop"})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["created"] == 3
        assert payload["batch_id"]
        assert len(payload["results"]) == 3

    def test_duplicate_in_the_same_batch_is_reported(self, client, sample_bytes) -> None:  # noqa: ANN001
        data = sample_bytes("market-breadth-2026.csv")
        files = [
            ("files", ("a.csv", data, "text/csv")),
            ("files", ("b.csv", data, "text/csv")),
        ]
        payload = client.post("/api/import/files", files=files).json()
        assert payload["created"] == 1
        assert payload["duplicates"] == 1
        duplicate = next(r for r in payload["results"] if r["status"] == "duplicate")
        assert duplicate["duplicate_of_id"]
        assert duplicate["duplicate_of_title"]

    def test_rejected_file_does_not_abort_the_batch(self, client, sample_bytes) -> None:  # noqa: ANN001
        files = [
            ("files", ("good.md", b"# Fine\n\nBody.", "text/markdown")),
            ("files", ("bad.pdf", b"definitely not a pdf", "application/pdf")),
            ("files", ("chart.png", tiny_png(), "image/png")),
        ]
        payload = client.post("/api/import/files", files=files).json()
        assert payload["created"] == 2
        assert payload["rejected"] == 1
        assert any("PDF" in r["message"] for r in payload["results"] if r["status"] == "rejected")

    def test_unreadable_file_lands_as_an_error_source(self, client) -> None:  # noqa: ANN001
        files = [("files", ("broken.pdf", b"%PDF-1.4\nbroken", "application/pdf"))]
        payload = client.post("/api/import/files", files=files).json()
        assert payload["errors"] == 1
        inbox = client.get("/api/inbox").json()
        assert len(inbox["failed"]) == 1
        assert inbox["failed"][0]["error_message"]

    def test_paste_import_with_tags(self, client) -> None:  # noqa: ANN001
        response = client.post(
            "/api/import/text",
            json={
                "text": "0:15 Host: Position sizing is a risk decision.\n1:02 Guest: Agreed.",
                "title": "Pasted transcript",
                "tags": ["demo-paste", "process"],
            },
        )
        assert response.status_code == 200
        source_id = response.json()["results"][0]["source_id"]
        detail = client.get(f"/api/sources/{source_id}").json()
        assert detail["kind"] == "transcript"
        assert {t["slug"] for t in detail["tags"]} == {"demo-paste", "process"}

    def test_empty_paste_is_rejected_with_400(self, client) -> None:  # noqa: ANN001
        assert client.post("/api/import/text", json={"text": "  "}).status_code == 422

    def test_batch_size_limit(self, client, monkeypatch) -> None:  # noqa: ANN001
        from app.config import reset_settings_cache

        monkeypatch.setenv("FORGE_MAX_BATCH_FILES", "1")
        reset_settings_cache()
        try:
            files = [("files", (f"n{i}.md", b"# x\n\ny", "text/markdown")) for i in range(2)]
            response = client.post("/api/import/files", files=files)
            assert response.status_code == 400
            assert "limited to" in response.json()["detail"]
        finally:
            monkeypatch.delenv("FORGE_MAX_BATCH_FILES")
            reset_settings_cache()


class TestReviewFlow:
    def test_review_payload_exposes_candidates(self, client, sample_bytes) -> None:  # noqa: ANN001
        files = [("files", ("helios.pdf", sample_bytes("helios-q3-fy2026-review.pdf"), "application/pdf"))]
        source_id = client.post("/api/import/files", files=files).json()["results"][0]["source_id"]

        payload = client.get(f"/api/sources/{source_id}/review").json()
        assert payload["source"]["status"] == "needs_review"
        assert payload["preview"]
        assert payload["documents"] >= 2
        assert isinstance(payload["entity_candidates"], list)

    def test_submitting_review_marks_ready_and_attaches_entities(self, client, sample_bytes) -> None:  # noqa: ANN001
        files = [("files", ("helios.pdf", sample_bytes("helios-q3-fy2026-review.pdf"), "application/pdf"))]
        source_id = client.post("/api/import/files", files=files).json()["results"][0]["source_id"]

        response = client.post(
            f"/api/sources/{source_id}/review",
            json={
                "title": "Helios Q3 FY2026 review",
                "author": "Demo Research Desk",
                "published_on": "2026-07-24",
                "tags": ["earnings", "hlsx"],
                "confirmed_entities": [
                    {"kind": "ticker", "name": "HLSX", "count": 4, "detector": "regex:ticker"},
                    {"kind": "company", "name": "Helios Semiconductor Inc.", "detector": "user"},
                ],
            },
        )
        assert response.status_code == 200, response.text
        source = response.json()
        assert source["status"] == "ready"
        assert source["title"] == "Helios Q3 FY2026 review"

        detail = client.get(f"/api/sources/{source_id}/detail").json()
        assert {e["name"] for e in detail["entities"]} == {"HLSX", "Helios Semiconductor Inc."}
        assert all(e["confirmed"] for e in detail["entities"])

    def test_inbox_empties_after_review(self, client, sample_bytes) -> None:  # noqa: ANN001
        files = [("files", ("rules.md", sample_bytes("swing-trading-rules.md"), "text/markdown"))]
        source_id = client.post("/api/import/files", files=files).json()["results"][0]["source_id"]
        assert len(client.get("/api/inbox").json()["pending"]) == 1

        client.post(f"/api/sources/{source_id}/review", json={})
        assert client.get("/api/inbox").json()["pending"] == []


class TestLibrary:
    def test_filters_and_facets(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/sources", params={"kind": ["pdf", "image"]}).json()
        assert payload["total"] == 2
        assert set(payload["facets"]["kind"]) >= {"pdf", "markdown", "csv"}

    def test_tag_filter(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/sources", params={"tag": ["hlsx"]}).json()
        assert payload["total"] >= 2
        for item in payload["items"]:
            assert "hlsx" in {t["slug"] for t in item["tags"]}

    def test_entity_filter(self, seeded) -> None:  # noqa: ANN001
        entities = seeded.get("/api/entities", params={"kind": "ticker"}).json()["items"]
        hlsx = next(e for e in entities if e["name"] == "HLSX")
        payload = seeded.get("/api/sources", params={"entity_id": [hlsx["id"]]}).json()
        assert payload["total"] >= 1

    def test_text_query_and_sorting(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/sources", params={"q": "Helios", "sort": "title_asc"}).json()
        assert payload["total"] >= 1
        titles = [i["title"] for i in payload["items"]]
        assert titles == sorted(titles)

    def test_pagination_metadata(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/sources", params={"page_size": 2, "page": 1}).json()
        assert len(payload["items"]) == 2
        assert payload["pages"] >= 2

    def test_detail_contains_documents_excerpts_and_links(self, seeded) -> None:  # noqa: ANN001
        source = seeded.get("/api/sources", params={"kind": "pdf"}).json()["items"][0]
        detail = seeded.get(f"/api/sources/{source['id']}/detail").json()
        assert detail["documents"]
        assert detail["excerpts"]
        assert detail["excerpts"][0]["provenance"]["citation"]
        assert detail["entities"]

    def test_original_file_download(self, seeded) -> None:  # noqa: ANN001
        source = seeded.get("/api/sources", params={"kind": "pdf"}).json()["items"][0]
        response = seeded.get(f"/api/sources/{source['id']}/file", params={"download": True})
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF-")
        assert "attachment" in response.headers["content-disposition"]

    def test_text_endpoint_paginates(self, seeded) -> None:  # noqa: ANN001
        source = seeded.get("/api/sources", params={"kind": "pdf"}).json()["items"][0]
        payload = seeded.get(f"/api/sources/{source['id']}/text", params={"limit": 1000}).json()
        assert len(payload["text"]) <= 1000
        assert payload["has_more"] is True

    def test_metadata_editing(self, seeded) -> None:  # noqa: ANN001
        source = seeded.get("/api/sources", params={"kind": "csv"}).json()["items"][0]
        response = seeded.patch(
            f"/api/sources/{source['id']}",
            json={"title": "Breadth series (edited)", "author": "Desk", "language": "en"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Breadth series (edited)"

    def test_unknown_source_returns_404(self, client) -> None:  # noqa: ANN001
        assert client.get("/api/sources/nope/detail").status_code == 404

    def test_delete_removes_excerpts_and_orphan_blob(self, seeded) -> None:  # noqa: ANN001
        source = seeded.get("/api/sources", params={"kind": "transcript"}).json()["items"][0]
        response = seeded.delete(f"/api/sources/{source['id']}")
        assert response.status_code == 200
        assert response.json()["original_removed"] is True
        assert seeded.get(f"/api/sources/{source['id']}").status_code == 404


class TestExcerpts:
    def test_creating_an_excerpt_derives_its_locator(self, client, sample_bytes) -> None:  # noqa: ANN001
        files = [("files", ("helios.pdf", sample_bytes("helios-q3-fy2026-review.pdf"), "application/pdf"))]
        source_id = client.post("/api/import/files", files=files).json()["results"][0]["source_id"]
        text = client.get(f"/api/sources/{source_id}/text").json()["text"]
        needle = "Gross margin"
        start = text.find(needle)

        response = client.post(
            f"/api/sources/{source_id}/excerpts",
            json={"text": text[start : start + 60], "char_start": start, "char_end": start + 60,
                  "note": "margin driver"},
        )
        assert response.status_code == 201, response.text
        excerpt = response.json()
        assert excerpt["locator"]["page"] == 1
        assert excerpt["provenance"]["locator_label"] == "p. 1"
        assert excerpt["provenance"]["citation"]

    def test_excerpt_offsets_are_validated(self, client, sample_bytes) -> None:  # noqa: ANN001
        files = [("files", ("rules.md", sample_bytes("swing-trading-rules.md"), "text/markdown"))]
        source_id = client.post("/api/import/files", files=files).json()["results"][0]["source_id"]
        response = client.post(
            f"/api/sources/{source_id}/excerpts",
            json={"text": "x", "char_start": 10, "char_end": 5},
        )
        assert response.status_code == 422

    def test_excerpt_outside_the_text_is_rejected(self, client, sample_bytes) -> None:  # noqa: ANN001
        files = [("files", ("rules.md", sample_bytes("swing-trading-rules.md"), "text/markdown"))]
        source_id = client.post("/api/import/files", files=files).json()["results"][0]["source_id"]
        response = client.post(
            f"/api/sources/{source_id}/excerpts",
            json={"text": "x", "char_start": 0, "char_end": 10_000_000},
        )
        assert response.status_code == 400

    def test_excerpt_text_is_located_automatically(self, client) -> None:  # noqa: ANN001
        source_id = client.post(
            "/api/import/text", json={"text": "Alpha beta gamma delta epsilon.", "title": "Note"}
        ).json()["results"][0]["source_id"]
        response = client.post(f"/api/sources/{source_id}/excerpts", json={"text": "gamma delta"})
        assert response.status_code == 201
        assert response.json()["char_start"] == 11

    def test_unused_excerpt_filter(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/excerpts", params={"unused_only": True}).json()
        assert payload["total"] >= 0
        for item in payload["items"]:
            assert item["used_by"] == []

    def test_update_and_delete(self, seeded) -> None:  # noqa: ANN001
        excerpt = seeded.get("/api/excerpts").json()["items"][0]
        updated = seeded.patch(f"/api/excerpts/{excerpt['id']}", json={"note": "revised note"}).json()
        assert updated["note"] == "revised note"
        assert seeded.delete(f"/api/excerpts/{excerpt['id']}").status_code == 200
        assert seeded.get(f"/api/excerpts/{excerpt['id']}").status_code == 404


class TestPdfMetadataRoundTrip:
    def test_generated_pdf_metadata_is_read_back(self, client) -> None:  # noqa: ANN001
        data = text_pdf("Body paragraph one.\n\nBody paragraph two.", title="Synthetic note", author="QA")
        files = [("files", ("synthetic.pdf", data, "application/pdf"))]
        source_id = client.post("/api/import/files", files=files).json()["results"][0]["source_id"]
        source = client.get(f"/api/sources/{source_id}").json()
        assert source["title"] == "Synthetic note"
        assert source["author"] == "QA"
