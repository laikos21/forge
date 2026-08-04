"""API tests for knowledge objects, dossiers, comparisons, links and review."""

from __future__ import annotations

import datetime as dt


def first_excerpt(client):  # noqa: ANN001, ANN201
    return client.get("/api/excerpts").json()["items"][0]


class TestKnowledge:
    def test_create_with_evidence_and_tags(self, seeded) -> None:  # noqa: ANN001
        excerpt = first_excerpt(seeded)
        response = seeded.post(
            "/api/knowledge",
            json={
                "kind": "insight",
                "title": "Attach rate is the platform tell",
                "body": "Networking attach rate is the cleanest evidence of lock-in.",
                "confidence": 65,
                "tags": ["thesis"],
                "excerpt_ids": [excerpt["id"]],
            },
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["status"] == "draft"
        assert payload["origin"] == "user"
        assert len(payload["evidence"]) == 1
        assert payload["evidence"][0]["source_title"]
        assert payload["evidence"][0]["locator_label"]

    def test_status_is_validated_per_kind(self, client) -> None:  # noqa: ANN001
        bad = client.post(
            "/api/knowledge", json={"kind": "rule", "title": "R", "status": "supported"}
        )
        assert bad.status_code == 422

        good = client.post(
            "/api/knowledge", json={"kind": "hypothesis", "title": "H", "status": "supported"}
        )
        assert good.status_code == 201

    def test_default_status_per_kind(self, client) -> None:  # noqa: ANN001
        payload = client.post("/api/knowledge", json={"kind": "hypothesis", "title": "H"}).json()
        assert payload["status"] == "open"

    def test_resolving_a_hypothesis_sets_timestamp(self, seeded) -> None:  # noqa: ANN001
        hypothesis = seeded.get("/api/knowledge", params={"kind": "hypothesis"}).json()["items"][0]
        updated = seeded.patch(
            f"/api/knowledge/{hypothesis['id']}",
            json={"status": "supported", "resolved": True, "outcome": "Confirmed by two sources."},
        ).json()
        assert updated["status"] == "supported"
        assert updated["resolved_at"]
        assert updated["outcome"].startswith("Confirmed")

    def test_evidence_can_be_added_and_removed(self, seeded) -> None:  # noqa: ANN001
        knowledge = seeded.get("/api/knowledge", params={"kind": "note"}).json()["items"][0]
        excerpt = first_excerpt(seeded)
        added = seeded.post(
            f"/api/knowledge/{knowledge['id']}/evidence",
            json={"excerpt_id": excerpt["id"], "stance": "refutes", "note": "counterpoint"},
        ).json()
        link_id = added["evidence"][0]["id"]
        assert added["evidence"][0]["stance"] == "refutes"

        seeded.delete(f"/api/knowledge/{knowledge['id']}/evidence/{link_id}")
        after = seeded.get(f"/api/knowledge/{knowledge['id']}").json()
        assert after["evidence"] == []

    def test_filters(self, seeded) -> None:  # noqa: ANN001
        rules = seeded.get("/api/knowledge", params={"kind": "rule"}).json()
        assert rules["total"] >= 1
        assert {i["kind"] for i in rules["items"]} == {"rule"}

        without_evidence = seeded.get("/api/knowledge", params={"has_evidence": False}).json()
        assert all(i["evidence"] == [] for i in without_evidence["items"])

    def test_promote_excerpt_to_rule_links_source_and_dossier(self, seeded) -> None:  # noqa: ANN001
        excerpt = first_excerpt(seeded)
        dossier = seeded.get("/api/dossiers").json()["items"][0]
        response = seeded.post(
            f"/api/excerpts/{excerpt['id']}/promote",
            json={
                "kind": "rule",
                "title": "Promoted rule from an excerpt",
                "stance": "supports",
                "dossier_id": dossier["id"],
                "tags": ["promoted"],
            },
        )
        assert response.status_code == 201, response.text
        knowledge = response.json()
        assert knowledge["kind"] == "rule"
        assert knowledge["evidence"][0]["excerpt_id"] == excerpt["id"]

        detail = seeded.get(f"/api/knowledge/{knowledge['id']}/detail").json()
        assert any(link["relation"] == "derived_from" for link in detail["links"])

        dossier_detail = seeded.get(f"/api/dossiers/{dossier['id']}").json()
        assert any(i["target_id"] == knowledge["id"] for i in dossier_detail["items"])

    def test_delete(self, seeded) -> None:  # noqa: ANN001
        knowledge = seeded.get("/api/knowledge", params={"kind": "quote"}).json()["items"][0]
        assert seeded.delete(f"/api/knowledge/{knowledge['id']}").status_code == 200
        assert seeded.get(f"/api/knowledge/{knowledge['id']}").status_code == 404


class TestDossiers:
    def test_create_and_slug(self, client) -> None:  # noqa: ANN001
        first = client.post("/api/dossiers", json={"title": "Power infrastructure", "subject_kind": "theme"}).json()
        second = client.post("/api/dossiers", json={"title": "Power infrastructure"}).json()
        assert first["slug"] == "power-infrastructure"
        assert second["slug"] == "power-infrastructure-2"

    def test_lookup_by_slug_or_id(self, seeded) -> None:  # noqa: ANN001
        dossier = seeded.get("/api/dossiers").json()["items"][0]
        by_id = seeded.get(f"/api/dossiers/{dossier['id']}").json()
        by_slug = seeded.get(f"/api/dossiers/{dossier['slug']}").json()
        assert by_id["dossier"]["id"] == by_slug["dossier"]["id"]

    def test_detail_sections(self, seeded) -> None:  # noqa: ANN001
        dossier = next(
            d for d in seeded.get("/api/dossiers").json()["items"] if d["subject_kind"] == "company"
        )
        payload = seeded.get(f"/api/dossiers/{dossier['id']}").json()
        assert payload["dossier"]["bull_case"]
        assert payload["dossier"]["bear_case"]
        assert payload["dossier"]["risks"]
        assert payload["dossier"]["open_questions"]
        assert payload["claims"]
        assert payload["timeline"]
        assert payload["related_entities"]
        assert payload["linked_source_ids"]
        sections = {item["section"] for item in payload["items"]}
        assert {"sources", "evidence", "knowledge", "entities"} <= sections

    def test_claims_carry_evidence_with_provenance(self, seeded) -> None:  # noqa: ANN001
        dossier = next(
            d for d in seeded.get("/api/dossiers").json()["items"] if d["subject_kind"] == "company"
        )
        payload = seeded.get(f"/api/dossiers/{dossier['id']}").json()
        with_evidence = [c for c in payload["claims"] if c["evidence"]]
        assert with_evidence
        evidence = with_evidence[0]["evidence"][0]
        assert evidence["text"]
        assert evidence["source_title"]

    def test_item_add_and_remove(self, seeded) -> None:  # noqa: ANN001
        dossier = seeded.get("/api/dossiers").json()["items"][0]
        source = seeded.get("/api/sources", params={"kind": "json"}).json()["items"][0]
        added = seeded.post(
            f"/api/dossiers/{dossier['id']}/items",
            json={"target_type": "source", "target_id": source["id"], "section": "sources"},
        )
        assert added.status_code == 201
        item_id = added.json()["id"]
        assert seeded.delete(f"/api/dossiers/{dossier['id']}/items/{item_id}").status_code == 200

    def test_item_target_must_exist(self, seeded) -> None:  # noqa: ANN001
        dossier = seeded.get("/api/dossiers").json()["items"][0]
        response = seeded.post(
            f"/api/dossiers/{dossier['id']}/items",
            json={"target_type": "source", "target_id": "missing", "section": "sources"},
        )
        assert response.status_code == 422

    def test_claim_lifecycle(self, seeded) -> None:  # noqa: ANN001
        dossier = seeded.get("/api/dossiers").json()["items"][0]
        excerpt = first_excerpt(seeded)
        claim = seeded.post(
            f"/api/dossiers/{dossier['id']}/claims",
            json={"text": "Attach rate keeps rising", "stance": "bull", "confidence": 55},
        ).json()
        evidence = seeded.post(
            f"/api/dossiers/{dossier['id']}/claims/{claim['id']}/evidence",
            json={"excerpt_id": excerpt["id"], "stance": "supports"},
        )
        assert evidence.status_code == 201

        updated = seeded.patch(
            f"/api/dossiers/{dossier['id']}/claims/{claim['id']}",
            json={"confidence": 75, "stance": "neutral"},
        ).json()
        assert updated["confidence"] == 75
        assert seeded.delete(f"/api/dossiers/{dossier['id']}/claims/{claim['id']}").status_code == 200

    def test_timeline_events(self, seeded) -> None:  # noqa: ANN001
        dossier = seeded.get("/api/dossiers").json()["items"][0]
        event = seeded.post(
            f"/api/dossiers/{dossier['id']}/events",
            json={"occurred_on": "2026-08-01", "title": "Follow-up review", "kind": "decision"},
        )
        assert event.status_code == 201
        payload = seeded.get(f"/api/dossiers/{dossier['id']}").json()
        dates = [e["occurred_on"] for e in payload["timeline"]]
        assert dates == sorted(dates)

    def test_markdown_export_contains_every_section(self, seeded) -> None:  # noqa: ANN001
        dossier = next(
            d for d in seeded.get("/api/dossiers").json()["items"] if d["subject_kind"] == "company"
        )
        response = seeded.get(f"/api/dossiers/{dossier['id']}/export/markdown")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        markdown = response.text
        for heading in ("# ", "## Overview", "## Bull case", "## Bear case", "## Risks",
                        "## Open questions", "## Claims and evidence", "## Timeline"):
            assert heading in markdown
        assert "Demonstration content" in markdown

    def test_bundle_export_is_a_zip_with_sources(self, seeded) -> None:  # noqa: ANN001
        import io
        import zipfile

        dossier = next(
            d for d in seeded.get("/api/dossiers").json()["items"] if d["subject_kind"] == "company"
        )
        response = seeded.get(f"/api/dossiers/{dossier['id']}/export/bundle")
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = archive.namelist()
            assert any(n.endswith("dossier.md") for n in names)
            assert any("/sources/" in n for n in names)
            assert any(n.endswith("manifest.json") for n in names)

    def test_delete(self, client) -> None:  # noqa: ANN001
        dossier = client.post("/api/dossiers", json={"title": "Scratch"}).json()
        assert client.delete(f"/api/dossiers/{dossier['id']}").status_code == 200
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 404


class TestLinksAndEntities:
    def test_links_are_visible_from_both_ends(self, seeded) -> None:  # noqa: ANN001
        source = seeded.get("/api/sources", params={"kind": "pdf"}).json()["items"][0]
        dossier = seeded.get("/api/dossiers").json()["items"][0]
        created = seeded.post(
            "/api/links",
            json={
                "from_type": "source", "from_id": source["id"],
                "to_type": "dossier", "to_id": dossier["id"],
                "relation": "supports",
            },
        )
        assert created.status_code == 201

        outgoing = seeded.get("/api/links", params={"target_type": "source", "target_id": source["id"]}).json()
        incoming = seeded.get("/api/links", params={"target_type": "dossier", "target_id": dossier["id"]}).json()
        assert any(link["relation"] == "supports" and link["direction"] == "outgoing" for link in outgoing["items"])
        assert any(link["relation"] == "supported_by" and link["direction"] == "incoming" for link in incoming["items"])

    def test_symmetric_relation_is_not_duplicated(self, seeded) -> None:  # noqa: ANN001
        dossiers = seeded.get("/api/dossiers").json()["items"]
        payload = {
            "from_type": "dossier", "from_id": dossiers[1]["id"],
            "to_type": "dossier", "to_id": dossiers[0]["id"],
            "relation": "related_to",
        }
        first = seeded.post("/api/links", json=payload).json()
        second = seeded.post("/api/links", json=payload).json()
        assert first["id"] == second["id"]

    def test_self_link_is_rejected(self, seeded) -> None:  # noqa: ANN001
        dossier = seeded.get("/api/dossiers").json()["items"][0]
        response = seeded.post(
            "/api/links",
            json={"from_type": "dossier", "from_id": dossier["id"],
                  "to_type": "dossier", "to_id": dossier["id"], "relation": "related_to"},
        )
        assert response.status_code == 422

    def test_unknown_relation_is_rejected(self, seeded) -> None:  # noqa: ANN001
        dossiers = seeded.get("/api/dossiers").json()["items"]
        response = seeded.post(
            "/api/links",
            json={"from_type": "dossier", "from_id": dossiers[0]["id"],
                  "to_type": "dossier", "to_id": dossiers[1]["id"], "relation": "eats"},
        )
        assert response.status_code == 422

    def test_entity_detail_lists_sources(self, seeded) -> None:  # noqa: ANN001
        entity = next(
            e for e in seeded.get("/api/entities", params={"kind": "company"}).json()["items"]
        )
        detail = seeded.get(f"/api/entities/{entity['id']}").json()
        assert detail["sources"]
        assert any(link["relation"] == "has_ticker" for link in detail["links"])

    def test_entities_are_deduplicated_by_normalized_name(self, client) -> None:  # noqa: ANN001
        first = client.post("/api/entities", json={"kind": "company", "name": "Helios Semiconductor Inc."}).json()
        second = client.post("/api/entities", json={"kind": "company", "name": "helios semiconductor"}).json()
        assert first["id"] == second["id"]

    def test_tag_management(self, seeded) -> None:  # noqa: ANN001
        tags = seeded.get("/api/tags").json()["items"]
        assert any(t["slug"] == "demo" for t in tags)
        assert all("usage_count" in t for t in tags)

        demo = next(t for t in tags if t["slug"] == "demo")
        targets = seeded.get(f"/api/tags/{demo['slug']}/targets").json()
        assert targets["items"]


class TestComparisons:
    def test_seeded_comparison_ranks_numeric_dimensions(self, seeded) -> None:  # noqa: ANN001
        comparison = seeded.get("/api/comparisons").json()["items"][0]
        payload = seeded.get(f"/api/comparisons/{comparison['id']}").json()
        assert len(payload["subjects"]) == 3
        assert len(payload["dimensions"]) == 5
        assert payload["rankings"]
        weight_dimension = next(d for d in payload["dimensions"] if d["name"] == "Book weight")
        assert payload["rankings"][weight_dimension["id"]][0] == payload["subjects"][0]["id"]

    def test_full_lifecycle(self, seeded) -> None:  # noqa: ANN001
        entities = seeded.get("/api/entities", params={"kind": "ticker"}).json()["items"]
        created = seeded.post(
            "/api/comparisons",
            json={"title": "Two names", "subject_type": "entity", "dimensions": ["Liquidity"]},
        ).json()

        for entity in entities[:2]:
            created = seeded.post(
                f"/api/comparisons/{created['id']}/subjects",
                json={"target_type": "entity", "target_id": entity["id"]},
            ).json()
        assert len(created["subjects"]) == 2

        created = seeded.post(
            f"/api/comparisons/{created['id']}/dimensions",
            json={"name": "Conviction", "kind": "rating", "higher_is_better": True},
        ).json()
        dimension = next(d for d in created["dimensions"] if d["name"] == "Conviction")

        updated = seeded.put(
            f"/api/comparisons/{created['id']}/cells",
            json={
                "subject_id": created["subjects"][0]["id"],
                "dimension_id": dimension["id"],
                "numeric_value": "4.5",
            },
        ).json()
        key = f"{created['subjects'][0]['id']}:{dimension['id']}"
        assert updated["cells"][key]["numeric_value"] == "4.5"

        markdown = seeded.get(f"/api/comparisons/{created['id']}/export/markdown")
        assert markdown.status_code == 200
        assert "| **Conviction** |" in markdown.text

    def test_cell_must_belong_to_the_comparison(self, seeded) -> None:  # noqa: ANN001
        comparison = seeded.get("/api/comparisons").json()["items"][0]
        response = seeded.put(
            f"/api/comparisons/{comparison['id']}/cells",
            json={"subject_id": "nope", "dimension_id": "nope", "text_value": "x"},
        )
        assert response.status_code == 422


class TestReviewScreen:
    def test_dashboard_sections(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/review").json()
        assert payload["recent_imports"]
        assert payload["recent_dossiers"]
        assert "unprocessed" in payload
        assert payload["open_hypotheses"]
        assert payload["awaiting_review"]
        assert "loose_ends" in payload
        assert "deterministic" in payload["disclaimer"].lower()

    def test_suggestions_are_labelled_as_metadata_overlap(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/review/suggestions").json()
        assert payload["basis"] == "deterministic_metadata_overlap"
        for item in payload["items"]:
            assert item["kind"] == "metadata_overlap"
            assert item["explanation"]
            assert item["basis"] in {"shared_entities", "shared_tags"}

    def test_awaiting_review_includes_overdue_rules(self, client) -> None:  # noqa: ANN001
        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        client.post(
            "/api/knowledge",
            json={"kind": "rule", "title": "Overdue rule", "status": "active", "review_due_on": yesterday},
        )
        payload = client.get("/api/review").json()
        titles = [item["title"] for item in payload["awaiting_review"]]
        assert "Overdue rule" in titles
        assert payload["awaiting_review"][0]["overdue_days"] >= 1
