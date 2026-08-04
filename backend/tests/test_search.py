"""Search: query parsing, ranking, filters, grouping, index maintenance."""

from __future__ import annotations

import pytest
from app.domain import TargetType
from app.services import indexer, search
from app.services.search import HL_END, HL_START, SearchQueryError, parse_query


class TestQueryParsing:
    def test_bare_terms_are_anded(self) -> None:
        parsed = parse_query("breakout base")
        assert parsed.match == '"breakout" AND "base"'
        assert parsed.terms == ["breakout", "base"]

    def test_quoted_phrase_is_preserved(self) -> None:
        parsed = parse_query('"volume dry up"')
        assert parsed.match == '"volume dry up"'
        assert parsed.phrases == ["volume dry up"]

    def test_negation_becomes_not(self) -> None:
        parsed = parse_query("breakout -crypto")
        assert parsed.match == '"breakout" NOT "crypto"'
        assert parsed.excluded == ["crypto"]

    def test_prefix_search(self) -> None:
        assert parse_query("semis*").match == '"semis"*'

    def test_column_filter(self) -> None:
        assert parse_query("title:nvidia").match == 'title : "nvidia"'

    def test_fts_operators_are_neutralised(self) -> None:
        # Would be a syntax error if passed through to SQLite.
        parsed = parse_query('NEAR(a b) OR ^x "unbalanced')
        assert "NEAR(" not in parsed.match
        assert parsed.match.count('"') % 2 == 0

    @pytest.mark.parametrize("query", ["", "   ", "-onlynegative", "!!!"])
    def test_unusable_queries_raise(self, query: str) -> None:
        with pytest.raises(SearchQueryError):
            parse_query(query)


class TestSearchExecution:
    def test_finds_a_phrase_inside_a_pdf(self, seeded) -> None:  # noqa: ANN001
        response = seeded.get("/api/search", params={"q": '"gross margin"'})
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] >= 1
        assert any(r["ref_type"] == "source" for r in payload["results"])

    def test_snippets_carry_highlight_markers(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/search", params={"q": "inventory"}).json()
        assert payload["highlight"] == {"start": HL_START, "end": HL_END}
        assert any(HL_START in r["snippet"] for r in payload["results"])

    def test_negation_excludes_results(self, seeded) -> None:  # noqa: ANN001
        with_term = seeded.get("/api/search", params={"q": "margin"}).json()["total"]
        without = seeded.get("/api/search", params={"q": "margin -inventory"}).json()["total"]
        assert without < with_term

    def test_filter_by_ref_type(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/search", params={"q": "margin", "types": ["excerpt"]}).json()
        assert payload["results"]
        assert {r["ref_type"] for r in payload["results"]} == {"excerpt"}

    def test_filter_by_source(self, seeded) -> None:  # noqa: ANN001
        sources = seeded.get("/api/sources", params={"kind": "pdf"}).json()["items"]
        source_id = sources[0]["id"]
        payload = seeded.get(
            "/api/search", params={"q": "margin", "source_ids": [source_id]}
        ).json()
        assert payload["results"]
        assert all(r["source_id"] == source_id for r in payload["results"])

    def test_results_carry_provenance(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/search", params={"q": "margin", "types": ["excerpt"]}).json()
        provenance = payload["results"][0]["provenance"]
        assert provenance["source_id"]
        assert provenance["source_title"]
        assert provenance["locator_label"]

    def test_grouping_by_source(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/search", params={"q": "margin", "group": True}).json()
        assert payload["groups"]
        for group in payload["groups"]:
            assert group["results"]

    def test_ranking_prefers_title_matches(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/search", params={"q": "Helios"}).json()
        assert payload["results"]
        assert "Helios" in payload["results"][0]["title"]

    def test_pagination(self, seeded) -> None:  # noqa: ANN001
        first = seeded.get("/api/search", params={"q": "the", "limit": 2}).json()
        second = seeded.get("/api/search", params={"q": "the", "limit": 2, "offset": 2}).json()
        assert len(first["results"]) <= 2
        if first["total"] > 2:
            assert first["results"][0]["ref_id"] != second["results"][0]["ref_id"]

    def test_invalid_query_returns_400(self, seeded) -> None:  # noqa: ANN001
        assert seeded.get("/api/search", params={"q": "   "}).status_code == 400

    def test_no_match_returns_empty_not_error(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/search", params={"q": "zzzzunlikelyzzz"}).json()
        assert payload["total"] == 0
        assert payload["results"] == []

    def test_diacritics_are_folded(self, client) -> None:  # noqa: ANN001
        client.post("/api/import/text", json={"text": "La expansión del margen fue por mezcla.", "title": "Nota"})
        assert client.get("/api/search", params={"q": "expansion"}).json()["total"] >= 1


class TestSuggestAndStatus:
    def test_title_suggestions(self, seeded) -> None:  # noqa: ANN001
        items = seeded.get("/api/search/suggest", params={"q": "Heli"}).json()["items"]
        assert any("Helios" in item for item in items)

    def test_short_prefix_returns_nothing(self, seeded) -> None:  # noqa: ANN001
        assert seeded.get("/api/search/suggest", params={"q": "H"}).json()["items"] == []

    def test_status_reports_engine_and_semantic_state(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/search/status").json()
        assert payload["fulltext"]["engine"] == "sqlite-fts5"
        assert payload["fulltext"]["indexed_objects"] > 0
        assert payload["semantic"]["enabled"] is False

    def test_semantic_search_is_inert_when_disabled(self, seeded) -> None:  # noqa: ANN001
        payload = seeded.get("/api/search/semantic", params={"q": "power constraints"}).json()
        assert payload["enabled"] is False
        assert payload["results"] == []


class TestIndexMaintenance:
    def test_index_covers_every_indexable_object(self, seeded) -> None:  # noqa: ANN001
        integrity = seeded.get("/api/maintenance/integrity").json()
        assert integrity["index"]["entries"] == integrity["index"]["expected"]

    def test_rebuild_is_idempotent(self, seeded) -> None:  # noqa: ANN001
        before = seeded.get("/api/search/status").json()["fulltext"]["indexed_objects"]
        rebuilt = seeded.post("/api/search/reindex").json()
        assert rebuilt["total"] == before

    def test_deleting_a_source_removes_it_from_the_index(self, seeded) -> None:  # noqa: ANN001
        source = seeded.get("/api/sources", params={"kind": "csv"}).json()["items"][0]
        seeded.delete(f"/api/sources/{source['id']}")
        payload = seeded.get("/api/search", params={"q": "pct_above_50dma"}).json()
        assert all(r["source_id"] != source["id"] for r in payload["results"])

    def test_editing_a_knowledge_object_updates_the_index(self, seeded) -> None:  # noqa: ANN001
        knowledge = seeded.get("/api/knowledge", params={"kind": "insight"}).json()["items"][0]
        seeded.patch(f"/api/knowledge/{knowledge['id']}", json={"title": "Chartreuse invariant"})
        payload = seeded.get("/api/search", params={"q": "chartreuse"}).json()
        assert payload["total"] >= 1

    def test_indexer_removes_unknown_refs(self, session) -> None:  # noqa: ANN001
        assert indexer.reindex_object(session, TargetType.SOURCE, "does-not-exist") is False


class TestGrouping:
    def test_group_by_source_merges_hits(self) -> None:
        hits = [
            search.SearchHit("excerpt", "e1", "s1", "excerpt", "a", "", -3.0),
            search.SearchHit("excerpt", "e2", "s1", "excerpt", "b", "", -1.0),
            search.SearchHit("source", "s2", "s2", "pdf", "c", "", -2.0),
        ]
        groups = search.group_by_source(hits)
        assert len(groups) == 2
        assert groups[0]["best_score"] == -3.0
        assert len(groups[0]["hits"]) == 2
