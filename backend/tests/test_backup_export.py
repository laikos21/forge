"""Backup, restore, export and the optional-intelligence fallbacks."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from app.services import backup as backup_service


class TestBackupRoundTrip:
    def test_backup_contains_database_files_and_manifest(self, seeded) -> None:  # noqa: ANN001
        response = seeded.post("/api/backups", json={"label": "test"})
        assert response.status_code == 201, response.text
        name = response.json()["name"]

        archive = seeded.get(f"/api/backups/{name}/download")
        assert archive.status_code == 200
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zip_file:
            names = zip_file.namelist()
            assert "forge.db" in names
            assert "manifest.json" in names
            assert "export.json" in names
            assert any(n.startswith("files/") for n in names)
            manifest = json.loads(zip_file.read("manifest.json"))
            assert manifest["format"] == "forge.backup"
            assert manifest["counts"]["source"] >= 7
            assert manifest["file_count"] >= 7

    def test_restore_recovers_deleted_data(self, seeded) -> None:  # noqa: ANN001
        before = seeded.get("/api/maintenance/counts").json()
        name = seeded.post("/api/backups", json={}).json()["name"]

        for source in seeded.get("/api/sources").json()["items"]:
            seeded.delete(f"/api/sources/{source['id']}")
        for dossier in seeded.get("/api/dossiers").json()["items"]:
            seeded.delete(f"/api/dossiers/{dossier['id']}")
        assert seeded.get("/api/maintenance/counts").json()["source"] == 0

        result = seeded.post(f"/api/backups/{name}/restore")
        assert result.status_code == 200, result.text
        payload = result.json()
        assert payload["safety_backup"]
        assert payload["counts"]["source"] == before["source"]

        after = seeded.get("/api/maintenance/counts").json()
        assert after == before

    def test_restored_originals_are_readable(self, seeded) -> None:  # noqa: ANN001
        name = seeded.post("/api/backups", json={}).json()["name"]
        source = seeded.get("/api/sources", params={"kind": "pdf"}).json()["items"][0]
        seeded.delete(f"/api/sources/{source['id']}")

        seeded.post(f"/api/backups/{name}/restore")
        restored = seeded.get(f"/api/sources/{source['id']}/file")
        assert restored.status_code == 200
        assert restored.content.startswith(b"%PDF-")

    def test_search_works_after_restore(self, seeded) -> None:  # noqa: ANN001
        name = seeded.post("/api/backups", json={}).json()["name"]
        for source in seeded.get("/api/sources").json()["items"]:
            seeded.delete(f"/api/sources/{source['id']}")
        seeded.post(f"/api/backups/{name}/restore")

        payload = seeded.get("/api/search", params={"q": '"gross margin"'}).json()
        assert payload["total"] >= 1

    def test_restore_creates_a_safety_backup_first(self, seeded) -> None:  # noqa: ANN001
        name = seeded.post("/api/backups", json={}).json()["name"]
        seeded.post(f"/api/backups/{name}/restore")
        backups = seeded.get("/api/backups").json()["items"]
        assert any("pre-restore" in b["name"] for b in backups)

    def test_deleting_a_backup(self, seeded) -> None:  # noqa: ANN001
        name = seeded.post("/api/backups", json={}).json()["name"]
        assert seeded.delete(f"/api/backups/{name}").status_code == 200
        assert all(b["name"] != name for b in seeded.get("/api/backups").json()["items"])

    def test_unknown_backup_returns_404(self, seeded) -> None:  # noqa: ANN001
        assert seeded.get("/api/backups/not-there.zip/download").status_code == 404


class TestRestoreValidation:
    def test_non_zip_upload_is_rejected(self, seeded) -> None:  # noqa: ANN001
        response = seeded.post(
            "/api/backups/upload-restore",
            files={"file": ("bad.zip", b"not a zip file at all", "application/zip")},
        )
        assert response.status_code == 422
        assert "zip" in response.json()["detail"].lower()

    def test_foreign_archive_is_rejected(self, seeded, tmp_path) -> None:  # noqa: ANN001
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"format": "something.else"}))
            archive.writestr("forge.db", b"x")
        response = seeded.post(
            "/api/backups/upload-restore",
            files={"file": ("foreign.zip", buffer.getvalue(), "application/zip")},
        )
        assert response.status_code == 422
        assert "FORGE backup" in response.json()["detail"]

    def test_newer_format_version_is_refused(self, tmp_path) -> None:  # noqa: ANN001
        path = tmp_path / "future.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "manifest.json",
                json.dumps({"format": "forge.backup", "format_version": 99}),
            )
            archive.writestr("forge.db", b"x")
        with pytest.raises(backup_service.RestoreError, match="newer than this build"):
            backup_service.inspect_archive(path)

    def test_corrupt_database_leaves_the_current_state_intact(self, seeded, tmp_path) -> None:  # noqa: ANN001
        before = seeded.get("/api/maintenance/counts").json()
        path = tmp_path / "corrupt.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "manifest.json",
                json.dumps({"format": "forge.backup", "format_version": 1, "counts": {}}),
            )
            archive.writestr("forge.db", b"SQLite format 3\x00 but truncated")

        response = seeded.post(
            "/api/backups/upload-restore",
            files={"file": ("corrupt.zip", path.read_bytes(), "application/zip")},
        )
        assert response.status_code == 422
        assert seeded.get("/api/maintenance/counts").json() == before

    def test_path_traversal_in_archive_is_refused(self, seeded, tmp_path) -> None:  # noqa: ANN001
        path = tmp_path / "evil.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "manifest.json", json.dumps({"format": "forge.backup", "format_version": 1})
            )
            archive.writestr("forge.db", b"x")
            archive.writestr("files/../../escape.txt", b"nope")
        response = seeded.post(
            "/api/backups/upload-restore",
            files={"file": ("evil.zip", path.read_bytes(), "application/zip")},
        )
        assert response.status_code == 422
        assert "unsafe path" in response.json()["detail"]


class TestExports:
    def test_json_export_covers_every_table(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/export/json", params={"download": False}).json()
        assert payload["format"] == "forge.json-export"
        assert payload["counts"]["source"] >= 7
        assert payload["counts"]["dossier"] == 2
        assert payload["counts"]["knowledge_object"] >= 6
        assert payload["tables"]["excerpt"][0]["locator_json"] is not None

    def test_source_markdown_export_has_front_matter_and_excerpts(self, seeded) -> None:  # noqa: ANN001
        source = seeded.get("/api/sources", params={"kind": "pdf"}).json()["items"][0]
        response = seeded.get(f"/api/export/sources/{source['id']}/markdown")
        assert response.status_code == 200
        text = response.text
        assert text.startswith("---")
        assert "content_sha256:" in text
        assert "## Excerpts" in text
        assert "## Extracted text" in text

    def test_selected_sources_bundle(self, seeded) -> None:  # noqa: ANN001
        ids = [s["id"] for s in seeded.get("/api/sources").json()["items"][:2]]
        response = seeded.post("/api/export/sources", json={"source_ids": ids, "include_originals": True})
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = archive.namelist()
            assert sum(1 for n in names if n.startswith("sources/")) == 2
            assert any(n.startswith("originals/") for n in names)
            manifest = json.loads(archive.read("manifest.json"))
            assert len(manifest["sources"]) == 2

    def test_unknown_source_export_is_404(self, seeded) -> None:  # noqa: ANN001
        response = seeded.post("/api/export/sources", json={"source_ids": ["missing"]})
        assert response.status_code == 404

    def test_knowledge_markdown_marks_generated_content(self, client) -> None:  # noqa: ANN001
        created = client.post(
            "/api/knowledge",
            json={
                "kind": "insight",
                "title": "Drafted insight",
                "body": "Body text.",
                "origin": "generated",
                "generated_by": "ollama:llama3.1:8b",
            },
        ).json()
        text = client.get(f"/api/export/knowledge/{created['id']}/markdown").text
        assert "[generated]" in text
        assert "ollama:llama3.1:8b" in text


class TestOptionalIntelligence:
    def test_status_reports_disabled_by_default(self, client) -> None:  # noqa: ANN001
        payload = client.get("/api/intelligence/status").json()
        assert payload["enabled"] is False
        assert payload["provider"]["available"] is False
        assert len(payload["operations"]) == 6

    def test_status_does_not_touch_the_network_when_disabled(self, client, monkeypatch) -> None:  # noqa: ANN001
        """A disabled provider must never cost a connection timeout."""

        import httpx

        def explode(*args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("the provider was probed while the feature was disabled")

        monkeypatch.setattr(httpx, "get", explode)
        monkeypatch.setattr(httpx, "post", explode)

        assert client.get("/api/intelligence/status").status_code == 200
        assert client.get("/api/settings/system").status_code == 200

    def test_explicit_probe_contacts_the_provider(self, client, monkeypatch) -> None:  # noqa: ANN001
        import httpx

        calls: list[str] = []

        def fake_get(url, **kwargs):  # noqa: ANN001, ANN003
            calls.append(url)
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "get", fake_get)
        payload = client.get("/api/intelligence/status", params={"probe": True}).json()
        assert calls, "probe=true must reach the provider"
        assert payload["provider"]["available"] is False
        assert "Could not reach Ollama" in payload["provider"]["detail"]

    def test_summarize_falls_back_to_extractive(self, seeded) -> None:  # noqa: ANN001
        source = seeded.get("/api/sources", params={"kind": "pdf"}).json()["items"][0]
        payload = seeded.post(
            "/api/intelligence/run", json={"operation": "summarize", "source_id": source["id"]}
        ).json()
        assert payload["method"] == "deterministic"
        assert payload["generated"] is False
        assert payload["text"]
        assert payload["provider"] == "forge"

        full_text = seeded.get(f"/api/sources/{source['id']}/text", params={"limit": 200000}).json()["text"]
        for sentence in payload["text"].split(". "):
            assert sentence.strip(". ") in full_text

    def test_entity_extraction_falls_back_to_patterns(self, seeded) -> None:  # noqa: ANN001
        source = seeded.get("/api/sources", params={"kind": "pdf"}).json()["items"][0]
        payload = seeded.post(
            "/api/intelligence/run", json={"operation": "extract_entities", "source_id": source["id"]}
        ).json()
        assert payload["method"] == "deterministic"
        assert payload["items"]
        assert all(item["grounded"] for item in payload["items"])

    def test_claim_extraction_quotes_verbatim(self, seeded) -> None:  # noqa: ANN001
        source = seeded.get("/api/sources", params={"kind": "pdf"}).json()["items"][0]
        payload = seeded.post(
            "/api/intelligence/run", json={"operation": "extract_claims", "source_id": source["id"]}
        ).json()
        full_text = seeded.get(f"/api/sources/{source['id']}/text", params={"limit": 200000}).json()["text"]
        assert payload["items"]
        for item in payload["items"]:
            assert item["quote"] in full_text

    def test_questions_fall_back_to_structural_gaps(self, seeded) -> None:  # noqa: ANN001
        dossier = seeded.get("/api/dossiers").json()["items"][0]
        payload = seeded.post(
            "/api/intelligence/run", json={"operation": "generate_questions", "dossier_id": dossier["id"]}
        ).json()
        assert payload["method"] == "deterministic"
        assert all("reason" in item for item in payload["items"])

    def test_comparison_draft_returns_an_empty_grid_not_a_guess(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.post(
            "/api/intelligence/run",
            json={
                "operation": "draft_comparison",
                "title": "Two names",
                "subjects": [{"label": "A", "context": "ctx"}, {"label": "B", "context": "ctx"}],
                "dimensions": ["Moat", "Risk"],
            },
        ).json()
        assert payload["method"] == "deterministic"
        assert len(payload["items"]) == 4
        assert all(item["value"] == "" for item in payload["items"])

    def test_missing_target_is_a_validation_error(self, client) -> None:  # noqa: ANN001
        assert client.post("/api/intelligence/run", json={"operation": "summarize"}).status_code == 422

    def test_generation_log_is_empty_without_a_provider(self, seeded) -> None:  # noqa: ANN001
        source = seeded.get("/api/sources").json()["items"][0]
        seeded.post("/api/intelligence/run", json={"operation": "summarize", "source_id": source["id"]})
        assert seeded.get("/api/intelligence/generations").json()["items"] == []


class TestSettings:
    def test_defaults_and_schema(self, client) -> None:  # noqa: ANN001
        payload = client.get("/api/settings").json()
        assert payload["values"]["llm.enabled"] is False
        assert payload["values"]["ui.theme"] == "dark"
        assert any(item["key"] == "semantic.enabled" for item in payload["schema"])

    def test_update_and_reset(self, client) -> None:  # noqa: ANN001
        updated = client.put("/api/settings", json={"values": {"ui.density": "compact", "llm.model": "qwen2.5:7b"}}).json()
        assert updated["values"]["ui.density"] == "compact"
        assert updated["values"]["llm.model"] == "qwen2.5:7b"

        reset = client.post("/api/settings/reset").json()
        assert reset["values"]["ui.density"] == "comfortable"

    def test_unknown_key_is_rejected(self, client) -> None:  # noqa: ANN001
        assert client.put("/api/settings", json={"values": {"nope": 1}}).status_code == 422

    def test_invalid_choice_falls_back_to_default(self, client) -> None:  # noqa: ANN001
        payload = client.put("/api/settings", json={"values": {"ui.theme": "neon"}}).json()
        assert payload["values"]["ui.theme"] == "dark"

    def test_system_info_reports_local_state(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/settings/system").json()
        assert payload["migration"]["current"] == payload["migration"]["head"]
        assert payload["storage"]["file_count"] >= 7
        assert payload["ocr"]["available"] in (True, False)
        assert payload["llm"]["available"] is False
        assert payload["semantic"]["enabled"] is False
