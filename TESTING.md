# Testing

```powershell
.\test.ps1                        # everything
.\test.ps1 -Backend               # pytest only
.\test.ps1 -Frontend              # tsc + vitest only
.\test.ps1 -Backend -Filter search
.\test.ps1 -Verbose2              # individual test names
```

## Current state

| Suite | Command | Tests | Result |
| --- | --- | --- | --- |
| Backend | `pytest` | 224 | pass |
| Frontend types | `tsc --noEmit -p tsconfig.app.json` | — | no errors |
| Frontend | `vitest run` | 83 | pass |

Backend ~40 s (dominated by real PDF parsing and real backup/restore cycles),
frontend ~1.5 s.

## Principles

**No mocks for anything FORGE owns.** Tests run against a real SQLite database,
a real file store, real PDF/PNG/CSV/JSON fixtures and the real HTTP stack via
`TestClient`. The only patched things are `httpx.get`/`httpx.post` in the two
tests that assert the *absence* of a network call and the handling of a refused
connection — which is the point of those tests.

**Isolation by directory.** `conftest.py` points `FORGE_DATA_DIR` at a fresh
`tmp_path` for every test and resets the settings cache and the engine. Your
real `data\` directory is never touched, and tests cannot leak state into each
other.

**Fixtures are the shipped samples.** The suite imports the same files in
`samples\` that the seed uses, so a break in extraction fails the tests and the
demo together.

## Backend layout

| File | Covers |
| --- | --- |
| `test_lib.py` | Text normalisation, slugs, language detection, extractive summary, ticker/date detection, hashing, filename sanitisation, magic-byte sniffing, path escape, locator labels, and the custom column types (UTC round-trip, exact decimals). |
| `test_extraction.py` | Every format: PDF pages and metadata, Markdown sections and front matter, transcript timestamps (inline, WebVTT, wrapped lines), CSV header/delimiter detection, JSON records and JSON Lines, image metadata, HTML stripping, cp1252 decoding. Plus the offset invariant for each. |
| `test_ingest.py` | The pipeline: storage of originals, document offsets, detected metadata, duplicate detection (exact and near), rejections (empty, oversized, wrong signature, pasted binary kind), the error path that keeps the file, reprocessing, and review. |
| `test_search.py` | Query parsing (phrases, negation, prefix, column filters, neutralised FTS operators, unusable queries), execution (filters, grouping, ranking, pagination, diacritic folding), suggestions, semantic-disabled behaviour, and index maintenance on create/edit/delete. |
| `test_api_library.py` | Import endpoints (batch, mixed success, duplicates, rejections, limits), the review flow, library filtering and facets, source detail, file download, metadata editing, deletion with blob cleanup, and excerpt CRUD including locator derivation and range validation. |
| `test_api_knowledge_dossiers.py` | Knowledge CRUD, per-kind status validation, evidence attach/detach, promotion of an excerpt, dossier CRUD, items, claims and evidence, timeline, Markdown and bundle export, bidirectional links, symmetric-link de-duplication, entity de-duplication, tags, comparisons (including decimal cells and ranking), and the review dashboard. |
| `test_backup_export.py` | Backup contents, restore recovering deleted data, restored originals and search, safety backups, and refusal of: non-zip, foreign archive, future format version, corrupt database, path traversal. Plus JSON/Markdown/bundle export, deterministic-fallback behaviour for all six operations, and settings. |
| `test_e2e_workflow.py` | The definition-of-done workflow end to end, and the seed. |

## The end-to-end smoke test

`test_full_research_workflow` walks the entire brief through the HTTP API:

```
import a PDF → verify text, documents and detected metadata are stored
review it (correct metadata, confirm entities) → status becomes ready
find it in search (grouped, with provenance)
quote a passage → excerpt carries "p. 1" and the source id
promote the excerpt → a rule with the excerpt as evidence
create a dossier → link source, excerpt and rule; add a claim with evidence; add an event
export → Markdown contains the quotation and its locator; the bundle contains sources + knowledge
back up → delete everything → restore → counts match exactly
verify the restored original file, search, dossier and evidence still work
integrity check reports healthy
```

`test_seed_creates_a_complete_worked_example` asserts the demo covers all seven
source kinds, both dossier subjects and all six knowledge kinds, that everything
is flagged and tagged as demonstration content, and that removing it leaves an
empty index.

**Why the smoke test is API-level rather than browser-driven.** A Playwright run
needs a browser download, which would make the test suite depend on network
access — the one thing the product is built to avoid. The API-level test covers
every state transition in the workflow; the browser layer is covered by the
frontend suite and by manual verification against a running build (recorded in
CHANGELOG). This is a deliberate trade, not an omission.

## Frontend layout

| File | Covers |
| --- | --- |
| `lib/format.test.ts` | Byte/number formatting, relative time across every branch, locator labels (same table as the backend), tone mapping, tag parsing, truncation, confidence bands. |
| `lib/highlight.test.ts` | Snippet splitting, unbalanced markers, local term highlighting, regex escaping, query-term extraction. |
| `lib/filters.test.ts` | URL round-trip, defaults omitted, invalid page, active-filter counting, descriptions. |
| `lib/api.test.ts` | Query building, JSON success, `ApiError` carrying backend detail, non-JSON error bodies, unreachable backend, JSON vs multipart request shapes, URL builders. |
| `lib/markdown.test.tsx` | Block parsing and rendering; asserts raw HTML in content is rendered as text, never as markup. |
| `components/ui.test.tsx` | Highlighted output (including script-looking content), empty/error/loading states and their ARIA roles, generated badges, provenance, segmented control, and the tag editor's full interaction. |
| `components/Modal.test.tsx` | Dialog semantics, focus placement in the body, Escape and close-button behaviour. |

## What is deliberately not tested

* **Ollama integration against a live model.** The provider is exercised through
  its failure paths (unavailable, unreachable, unparseable JSON); asserting on a
  model's output would be asserting on a moving target.
* **OCR output quality.** Tesseract's availability detection and the graceful
  degradation are tested; its accuracy is not FORGE's to guarantee.
* **Visual regression.** No screenshot diffing.

## Adding tests

Backend: `client` gives an empty database, `seeded` gives the demo corpus,
`session` gives a service-level session, `sample_bytes("name")` reads a shipped
fixture. `tests/helpers.py` builds synthetic PDFs and PNGs and finds phrases in
hard-wrapped extracted text.

Frontend: keep logic in `lib/` and test it there; reserve component tests for
behaviour a user performs (typing, clicking, focus, ARIA).
