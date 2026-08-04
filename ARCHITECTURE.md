# Architecture

This document explains *why* FORGE is shaped the way it is. For the schema see
[DATA_MODEL.md](DATA_MODEL.md); for the product-level calls see
[PRODUCT_DECISIONS.md](PRODUCT_DECISIONS.md).

## The constraint that shapes everything

> The system must be useful without any paid API, cloud service, external
> account or API key, and must work locally on Windows 11.

Three consequences follow, and they explain most of the design:

1. **The database is the whole backend.** No search service, no vector
   database, no queue, no cache. SQLite does storage, full-text search and
   transactions; the filesystem stores blobs.
2. **Every intelligent feature needs a deterministic floor.** A feature that
   only works with a local model installed is a feature most users never see, so
   each one has a non-model implementation that is honest about what it is.
3. **Nothing may block on the network.** Optional providers are probed only when
   the user has enabled them or explicitly asked to test the connection.

## Shape

```
 React 19 + TypeScript (Vite)          FastAPI + SQLAlchemy 2.0 (Python)
┌───────────────────────────┐        ┌────────────────────────────────────┐
│ pages/      screens       │        │ api/         routing + serialisation│
│ components/ presentation  │ HTTP   │ services/    business logic         │
│ lib/        api, format,  │──────► │ lib/         pure helpers           │
│             filters,      │  JSON  │ models.py    ORM                    │
│             markdown,     │        │ schemas.py   validation             │
│             hooks         │        └────────────────┬───────────────────┘
└───────────────────────────┘                         │
                                        ┌─────────────┴──────────────┐
                                        │ data\forge.db  (SQLite)    │
                                        │ data\files\    (originals) │
                                        │ data\backups\  (archives)  │
                                        └────────────────────────────┘
```

### Backend layers

| Layer | Rule | Example |
| --- | --- | --- |
| `api/` | HTTP only: parse, call a service, serialise. No business logic. | `routes_sources.py` |
| `services/` | All rules. Takes a `Session`, never sees a `Request`. | `ingest.py`, `search.py` |
| `lib/` | Pure functions. No database, no framework, no I/O except explicit paths. | `text.py`, `files.py` |
| `models.py` | ORM only. No behaviour beyond relationships. | |
| `schemas.py` | Request validation (`extra="forbid"`) and response shapes. | |

The separation is load-bearing: the extraction, search-query and provenance
logic is tested directly against `lib/` and `services/` with no HTTP involved,
which is why the suite runs in seconds.

### Frontend layers

| Layer | Rule |
| --- | --- |
| `lib/api.ts` | The only place that calls `fetch`. Errors normalised to `ApiError`. |
| `lib/*.ts` | Pure logic: formatting, filter serialisation, snippet splitting, Markdown parsing. Unit-tested without React. |
| `components/` | Presentation and interaction primitives. No data fetching except the picker, which is explicitly a search widget. |
| `pages/` | Compose components, own screen state, call `api`. |

"Business logic outside UI components" in practice: the library's filter state
lives in the URL and is parsed by `lib/filters.ts`; search highlighting is
`lib/highlight.ts` returning plain segments; locator labels are duplicated in
`lib/format.ts` so the frontend can render a locator without a round trip, and
both implementations are tested against the same table of cases.

## Request flow: importing a file

```
POST /api/import/files (multipart)
  routes_import.import_files
    ingest.ingest_bytes
      validate size and magic bytes            lib/files.detect_magic
      hash the bytes                           lib/hashing.sha256_bytes
      look for a duplicate                     source.content_hash / text_hash
      store the blob (content-addressed)       services/storage.save_blob
      extract                                  services/extraction/*  ->  units
      assemble text + offsets                  extraction/base.assemble
      detect metadata and entity candidates    lib/text, services/entities
      persist Source + Document rows
      index                                    services/indexer.index_source
  -> ImportItemResult per file
```

Two properties are deliberate:

* **Total**: every input produces a row. A file that cannot be parsed becomes a
  source in the `error` state with its bytes preserved, never a silent loss.
* **Offsets are defined, not guessed**: the normalized text of a source *is* the
  extracted units joined by a blank line, and `assemble()` computes both at
  once. An excerpt offset therefore always addresses the same characters the
  reader displays. Every extractor test asserts
  `text[unit.char_start:unit.char_end] == unit.text`.

## Extraction

One module per format behind a single `extract(kind, data, filename)` entry
point, each returning `DocumentUnit`s with a locator appropriate to the format:

| Format | Unit | Locator |
| --- | --- | --- |
| PDF (pypdf) | page | `{page: 4}` |
| Markdown | section | `{section: "Risks", level: 2}` |
| Transcript | speaker turn | `{timestamp: "12:30", timestamp_seconds: 750, speaker: "…"}` |
| CSV | row group | `{row_start: 26, row_end: 50, columns: [...]}` |
| JSON | record | `{pointer: "/positions", index: 3}` |
| Image | whole | `{region: "metadata"}` / `{region: "ocr"}` |
| Text / web article | block | `{block: 2}` |

Choosing pypdf over a native library (pdfium, poppler) costs some extraction
quality on complex layouts and buys a pure-Python install that needs no build
tools on Windows. For a research corpus of text-first documents that is the
right trade; a scanned PDF is detected and reported rather than silently
imported empty.

## Search

FTS5, one virtual table indexing composed documents:

```sql
CREATE VIRTUAL TABLE search_index USING fts5(
    ref_type UNINDEXED, ref_id UNINDEXED, source_id UNINDEXED, kind UNINDEXED,
    title, body,
    tokenize = 'unicode61 remove_diacritics 2'
);
```

* **Application-maintained, not trigger-maintained.** What FORGE indexes is a
  *composition* (a dossier's overview + thesis + bull + bear + risks; a source's
  text + author + detected tickers). Triggers only see raw columns. Keeping
  composition in Python makes it explicit, testable and rebuildable
  (`POST /api/search/reindex`), at the cost of remembering to call the indexer —
  which the integrity check verifies.
* **The user's query never reaches SQLite.** `parse_query` tokenises, then
  re-quotes every term. A stray `"` or `NEAR(` yields zero results, never a 500.
* **Ranking** is `bm25` with the title weighted 8× the body.
* **Highlighting** uses `snippet()` with U+001F/U+001E delimiters. The frontend
  splits on them and renders `<mark>`, so no HTML is ever parsed — highlighting
  cannot become an injection vector.

Semantic search sits behind `services/semantic.py`: `status()`, `build_index()`,
`query()`. Vectors are float32 blobs compared in Python. For a single-user
corpus of thousands of documents this is fast enough and avoids a native
extension; if the corpus grew past that, the adapter is the only thing that
would need to change.

## Optional intelligence

```
services/llm/
  base.py         LLMProvider protocol, ProviderStatus, NullProvider
  ollama.py       the one concrete provider (local HTTP, no key)
  operations.py   six operations, each with a deterministic fallback
```

`_try_generate` is the shared path: build a prompt, call the provider, parse
JSON, record a `generation` row. On any failure — disabled, unreachable,
unparseable output — the operation returns its deterministic result with
`fallback_reason` filled in, and the UI says which one it got.

Nothing generated is written to a user-visible field by these endpoints. The
client posts the edited draft back through the normal create/update endpoints,
which stamp `origin='generated'` and `generated_by`.

## Migrations

Alembic, with `app/migrations.py` wrapping the command API so migrations run
from three places with one implementation: application startup (`lifespan`),
`scripts/manage.py migrate`, and after a restore. The FTS5 virtual table is
created by hand in the migration and excluded from autogenerate comparison.

## Frontend data flow

No state-management library. `useAsync(loader, deps)` covers the pattern every
screen needs — loading, error, data, reload, superseded-request guarding — in
about forty lines. React Query would add caching and a dependency; for an app
where every screen is a fresh read of a local database that is not a trade worth
making.

The URL is the source of truth for filters and search, so any list view is
bookmarkable and survives the back button.

## Serving

In development, Vite proxies `/api` to uvicorn, so the frontend always uses
same-origin relative URLs. In production, FastAPI serves `frontend/dist` and the
SPA fallback from the same origin. There is no CORS in the deployed path at all;
the permissive dev origins exist only for the Vite server.
