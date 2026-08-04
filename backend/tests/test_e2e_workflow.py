"""End-to-end smoke test.

Walks the definition-of-done workflow through the real HTTP API against a real
SQLite database and a real file store, with no mocks anywhere:

    import a file -> review it -> find it in search -> quote an excerpt ->
    promote the excerpt to a rule -> link it to a dossier -> export the dossier ->
    back up -> destroy everything -> restore -> confirm it all came back.
"""

from __future__ import annotations

import io
import zipfile

from helpers import find_span


def test_full_research_workflow(client, sample_bytes) -> None:  # noqa: ANN001
    # 1. Import a PDF through the inbox.
    files = [("files", ("helios.pdf", sample_bytes("helios-q3-fy2026-review.pdf"), "application/pdf"))]
    import_result = client.post("/api/import/files", files=files, data={"batch_label": "E2E"})
    assert import_result.status_code == 200, import_result.text
    assert import_result.json()["created"] == 1
    source_id = import_result.json()["results"][0]["source_id"]

    # 2. The extracted text, documents and metadata are stored.
    detail = client.get(f"/api/sources/{source_id}/detail").json()
    assert detail["source"]["char_count"] > 1000
    assert detail["source"]["status"] == "needs_review"
    assert len(detail["documents"]) >= 2
    assert detail["detected_metadata"]["language"] == "en"

    # 3. Review it: correct the metadata and confirm entities.
    review = client.post(
        f"/api/sources/{source_id}/review",
        json={
            "title": "Helios Semiconductor - Q3 FY2026 review",
            "author": "Demo Research Desk",
            "published_on": "2026-07-24",
            "tags": ["earnings", "ai-compute"],
            "confirmed_entities": [
                {"kind": "ticker", "name": "HLSX", "detector": "user"},
                {"kind": "company", "name": "Helios Semiconductor Inc.", "detector": "user"},
            ],
        },
    )
    assert review.status_code == 200
    assert review.json()["status"] == "ready"

    # 4. Find it through search.
    search = client.get("/api/search", params={"q": '"gross margin"', "group": True}).json()
    assert search["total"] >= 1
    assert any(hit["source_id"] == source_id for hit in search["results"])
    assert any(group["source_id"] == source_id for group in search["groups"])

    # 5. Quote an excerpt, with provenance.
    text = client.get(f"/api/sources/{source_id}/text", params={"limit": 200000}).json()["text"]
    start, _ = find_span(text, "Gross margin expanded 240 basis points")
    end = text.find(".", start) + 1
    excerpt = client.post(
        f"/api/sources/{source_id}/excerpts",
        json={"text": text[start:end], "char_start": start, "char_end": end,
              "note": "Mix, not price."},
    ).json()
    assert excerpt["provenance"]["locator_label"].startswith("p.")
    assert excerpt["provenance"]["source_id"] == source_id

    # 6. Promote the excerpt into a rule.
    rule = client.post(
        f"/api/excerpts/{excerpt['id']}/promote",
        json={
            "kind": "rule",
            "title": "Treat mix-driven margin expansion as reversible",
            "body": "Mix-driven margin is not pricing power; require two more quarters before extrapolating.",
            "tags": ["margins"],
        },
    ).json()
    assert rule["kind"] == "rule"
    assert rule["evidence"][0]["excerpt_id"] == excerpt["id"]
    assert rule["evidence"][0]["source_title"]

    # 7. Create a dossier and link the source, the excerpt and the rule to it.
    dossier = client.post(
        "/api/dossiers",
        json={
            "title": "Helios Semiconductor (E2E)",
            "subject_kind": "company",
            "overview": "End-to-end test dossier.",
            "bull_case": "Operating leverage is real.",
            "bear_case": "Margin expansion is mix-driven.",
            "risks": "Customer power availability.",
            "open_questions": "Does inventory normalise?",
            "tags": ["e2e"],
        },
    ).json()
    for target_type, target_id, section in (
        ("source", source_id, "sources"),
        ("excerpt", excerpt["id"], "evidence"),
        ("knowledge", rule["id"], "knowledge"),
    ):
        added = client.post(
            f"/api/dossiers/{dossier['id']}/items",
            json={"target_type": target_type, "target_id": target_id, "section": section},
        )
        assert added.status_code == 201, added.text

    claim = client.post(
        f"/api/dossiers/{dossier['id']}/claims",
        json={"text": "Margin expansion is mix-driven", "stance": "bear", "confidence": 60},
    ).json()
    assert client.post(
        f"/api/dossiers/{dossier['id']}/claims/{claim['id']}/evidence",
        json={"excerpt_id": excerpt["id"], "stance": "supports"},
    ).status_code == 201
    assert client.post(
        f"/api/dossiers/{dossier['id']}/events",
        json={"occurred_on": "2026-07-24", "title": "Q3 results", "source_id": source_id},
    ).status_code == 201

    full = client.get(f"/api/dossiers/{dossier['id']}").json()
    assert full["counts"]["sources"] == 1
    assert full["claims"][0]["evidence"][0]["text"]
    assert any(entity["name"] == "HLSX" for entity in full["related_entities"])

    # 8. Export the dossier - Markdown and a bundle.
    markdown = client.get(f"/api/dossiers/{dossier['id']}/export/markdown")
    assert markdown.status_code == 200
    assert "Helios Semiconductor (E2E)" in markdown.text
    find_span(markdown.text, "Gross margin expanded 240 basis points")  # evidence quoted inline
    assert "p. 1" in markdown.text  # with its locator

    bundle = client.get(f"/api/dossiers/{dossier['id']}/export/bundle")
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert any(name.endswith("dossier.md") for name in archive.namelist())
        assert any("/knowledge/" in name for name in archive.namelist())

    # 9. Back up, destroy, restore.
    backup_name = client.post("/api/backups", json={"label": "e2e"}).json()["name"]
    counts_before = client.get("/api/maintenance/counts").json()

    client.delete(f"/api/sources/{source_id}")
    client.delete(f"/api/dossiers/{dossier['id']}")
    client.delete(f"/api/knowledge/{rule['id']}")
    assert client.get("/api/maintenance/counts").json()["source"] == 0

    restored = client.post(f"/api/backups/{backup_name}/restore")
    assert restored.status_code == 200, restored.text
    assert client.get("/api/maintenance/counts").json() == counts_before

    # 10. Everything is usable again after the restore.
    assert client.get(f"/api/sources/{source_id}/file").content.startswith(b"%PDF-")
    assert client.get("/api/search", params={"q": '"gross margin"'}).json()["total"] >= 1
    reopened = client.get(f"/api/dossiers/{dossier['id']}").json()
    assert reopened["counts"]["sources"] == 1
    assert client.get(f"/api/knowledge/{rule['id']}").json()["evidence"][0]["excerpt_id"] == excerpt["id"]

    integrity = client.get("/api/maintenance/integrity").json()
    assert integrity["dangling_references"] == []
    assert integrity["missing_original_files"] == []
    assert integrity["healthy"] is True


def test_seed_creates_a_complete_worked_example(client) -> None:  # noqa: ANN001
    result = client.post("/api/maintenance/seed", json={"reset": True}).json()
    assert result["status"] == "created"
    assert result["warnings"] == []

    home = client.get("/api/home").json()
    assert home["stats"]["sources"] == 7
    assert home["stats"]["dossiers"] == 2
    assert home["stats"]["knowledge"] == 6
    assert home["stats"]["excerpts"] >= 8

    kinds = {d["subject_kind"] for d in client.get("/api/dossiers").json()["items"]}
    assert {"company", "setup"} <= kinds

    knowledge_kinds = {k["kind"] for k in client.get("/api/knowledge").json()["items"]}
    assert {"insight", "rule", "hypothesis", "decision", "quote", "note"} <= knowledge_kinds

    source_kinds = {s["kind"] for s in client.get("/api/sources").json()["items"]}
    assert {"pdf", "transcript", "markdown", "csv", "json", "image", "web_article"} <= source_kinds

    for source in client.get("/api/sources").json()["items"]:
        assert source["is_demo"] is True
        assert "demo" in {tag["slug"] for tag in source["tags"]}
        assert source["status"] == "ready"

    integrity = client.get("/api/maintenance/integrity").json()
    assert integrity["healthy"] is True

    removed = client.delete("/api/maintenance/demo").json()
    assert removed["sources"] == 7
    assert removed["dossiers"] == 2
    assert client.get("/api/maintenance/counts").json()["source"] == 0
    assert client.get("/api/search/status").json()["fulltext"]["indexed_objects"] == 0
