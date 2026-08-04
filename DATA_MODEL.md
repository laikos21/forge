# Data model

25 tables plus one FTS5 virtual table. Schema revision `0001_initial`
(`backend/alembic/versions/0001_initial_schema.py`).

## Conventions

| Concern | Choice | Why |
| --- | --- | --- |
| Identifiers | UUID4 strings (`String(36)`) | Stable across backup/restore and across machines; the frontend can reference an object without waiting for a server-assigned integer. |
| Timestamps | `UtcDateTime` — ISO-8601 UTC text, always timezone-aware | SQLite has no datetime type. Storing an offset-naive local time is the classic way to lose an hour twice a year. |
| Calendar dates | `IsoDate` — `YYYY-MM-DD` text | A publication date has no timezone. Parsing it as an instant shifts it a day west of Greenwich, which the frontend also guards against. |
| Decimals | `DecimalText` — exact decimal as text | Comparison metrics and weights are user-entered numbers. They round-trip exactly; no binary float is involved. |
| Enumerations | Python `StrEnum` in `domain.py`, `String` columns | Values are validated in Pydantic and exposed at `/api/meta/vocabulary`. Adding one is a code change, not a migration. |
| Polymorphic refs | `(target_type, target_id)` pairs | See "Polymorphic references" below. |

## Sources and content

### `source`
The unit of import. One row per imported file or pasted text.

Identity and integrity: `content_hash` (SHA-256 of the original bytes) and
`text_hash` (SHA-256 of whitespace-collapsed, case-folded normalized text).
The first catches an identical re-import; the second catches the same article
pasted again with different line wrapping. Neither is unique — a forced import
is allowed and keeps both hashes, so duplicates remain *visible* rather than
prevented.

Content: `text` is the normalized full text and the coordinate space every
excerpt offset refers to. `storage_path` points at the preserved original under
`data\files\<hash[:2]>\<hash><ext>`.

Provenance of the extraction itself: `extraction_method` (`pypdf`,
`transcript_inline`, `markdown`, `csv`, `image+ocr`, …),
`extraction_warnings` (a scanned PDF, a CSV with no header, a stripped HTML
document), `detected_metadata` (everything the deterministic detectors found,
kept for auditing even after the user overrides it).

Lifecycle: `status` moves `processing → needs_review → ready`, or to `error`.
A source in `error` still has its original bytes and can be reprocessed.

### `document`
A structural unit of a source: a PDF page, a Markdown section, a transcript
turn, a group of CSV rows, a JSON record. Holds `ordinal`, `text`,
`char_start`, `char_end` and a `locator_json` shaped by the format.

The invariant that makes provenance real:

```
source.text[document.char_start : document.char_end] == document.text
```

Guaranteed by construction — `extraction/base.assemble()` builds the full text
and the offsets in one pass — and asserted for every format in the test-suite.

### `excerpt`
A verbatim span the user selected, with `char_start`/`char_end` into
`source.text`, a `locator_json` inherited from the containing document, the
creation time and `created_via` (the transformation method). Excerpts are what
knowledge objects and dossier claims are built from, which is how a conclusion
stays traceable to a page or a timestamp.

## Knowledge

### `knowledge_object`
One table with a `kind` discriminator: `insight`, `rule`, `hypothesis`,
`decision`, `quote`, `note`.

**Why one table.** The six kinds share every column that matters (title, body,
status, confidence, origin, review date, tags, evidence, links) and every
behaviour (search indexing, evidence attachment, dossier membership, export).
Five near-identical tables would multiply the linking tables by five and buy
nothing but joins. What differs is the *lifecycle*, and that is expressed as
`KNOWLEDGE_STATUSES` per kind, enforced in the API:

| Kind | Statuses |
| --- | --- |
| insight / quote / note | draft → active → archived |
| rule | draft → active → under_review → retired |
| hypothesis | open → supported / refuted / inconclusive |
| decision | proposed → made → executed → reviewed → reversed |

Kind-specific extras live in `data_json` (a decision's position weight, a rule's
scope). Attempting a status outside its kind's list is a 422.

`origin` (`user` / `generated` / `seed` / `import`) plus `generated_by` and
`generation_id` are what make generated content visibly generated everywhere it
appears, including in Markdown exports.

### `knowledge_excerpt`
The evidence edge, with a `stance` (`supports` / `refutes` / `context`) and an
optional note. Evidence that *undercuts* a claim is a first-class relationship,
not an absence.

## Entities

### `entity`
`company`, `ticker`, `person`, `topic`, `theme` in one table, unique on
`(kind, normalized_name)`. Normalisation strips accents, punctuation and legal
suffixes, so "Helios Semiconductor Inc." and "helios semiconductor" resolve to
the same row. `data_json` holds kind-specific fields (a ticker's exchange, a
company's sector). Company↔ticker is a `ticker_of` / `has_ticker` link rather
than a foreign key, because the same relationship vocabulary already exists.

### `entity_mention`
`(entity, source)` with an occurrence count, the `detector` that found it
(`regex:ticker`, `metadata:author`, `llm:<model>`, `user`) and a `confirmed`
flag. Detection proposes; the review screen decides. A ticker attached to a note
by accident is worse than no ticker, so nothing is attached without confirmation.

## Organisation

* **`tag` / `tagging`** — one tag vocabulary shared by every object type.
* **`collection` / `collection_item`** — ordered, ad-hoc groupings (a reading
  queue). Tags classify; collections sequence.
* **`link`** — the generic relationship table (see below).

## Dossiers

* **`dossier`** — the workspace. Prose sections (`overview`, `thesis`,
  `bull_case`, `bear_case`, `risks`, `open_questions`) are Markdown text
  columns, not child rows: they are edited as prose and exported as prose, so
  structure would be overhead.
* **`dossier_item`** — anything attached to a dossier, grouped by `section`
  (`sources`, `evidence`, `knowledge`, `entities`, `notes`, `watchlist`).
* **`dossier_claim`** — a discrete assertion with a `stance`
  (`bull`/`bear`/`risk`/`question`/`neutral`) and confidence. Claims are
  structured because they carry evidence; the prose sections are not.
* **`claim_evidence`** — an excerpt (preferred) or a whole source, with a stance.
* **`timeline_event`** — a dated event, optionally citing a source.

## Comparison

`comparison` → `comparison_subject` (polymorphic) × `comparison_dimension`
(typed: text / number / rating / boolean, with unit, weight and
`higher_is_better`) → `comparison_cell`. Numeric cells are `DecimalText`;
ranking is computed on read, never stored.

## Optional and infrastructure

* **`generation`** — an audit row for every local-LLM call: provider, model,
  operation, target, prompt, raw output, parsed result, duration, accepted flag.
  Nothing generated exists anywhere without a row here to point back at.
* **`embedding`** — optional local vectors (`ref_type`, `ref_id`, model, dim,
  float32 blob, norm). Empty and unused when semantic search is off; derived
  data, so it is excluded from the JSON export and rebuilt on demand.
* **`app_setting`** — user preferences as typed key/value rows.
* **`import_batch`** — groups one drag-and-drop of files.
* **`search_index`** — the FTS5 virtual table.

## Polymorphic references

`tagging`, `dossier_item`, `collection_item`, `comparison_subject` and `link`
all address "some object" as `(target_type, target_id)`.

**The tradeoff, stated plainly.** SQLite cannot enforce a foreign key on a
polymorphic pair. The alternative — a join table per (container, target) pair —
would mean roughly twenty extra tables and twenty extra code paths for the same
behaviour. FORGE takes the polymorphic pair and pays for it with:

* `services/refs.py` as the single resolver (`describe`, `exists`, `fetch`);
* existence validation in every service that creates such a row;
* cascade cleanup on delete in the same services;
* `GET /api/maintenance/integrity`, which walks every polymorphic table and
  reports dangling references, missing original files and index drift — exposed
  in Settings and asserted by the end-to-end test.

## Relationships

One `link` row per edge, stored in the direction the user created it:

```
(from_type, from_id) --relation--> (to_type, to_id)
```

Reads are bidirectional: `links.neighbours(type, id)` returns outgoing edges
as-is and incoming edges relabelled with their inverse from
`RELATION_INVERSES` — `supports`/`supported_by`, `derived_from`/`produced`,
`ticker_of`/`has_ticker`, `part_of`/`contains`, and symmetric relations
(`related_to`, `contradicts`, `competitor_of`) that read the same from both
ends. Creating a symmetric edge that already exists in the other direction
returns the existing row instead of a duplicate.

Storing one row per edge means an edge can never half-exist or drift out of
sync, at the cost of a slightly more complex read — which lives in exactly one
function.

## Provenance guarantee

Every derived object answers all four questions the brief requires:

| Question | Where it comes from |
| --- | --- |
| Which source? | `excerpt.source_id` → `source` |
| Where in it? | `excerpt.locator_json` + `char_start`/`char_end`, rendered by `lib/provenance.py` as `p. 4`, `[12:30]`, `§ Risks`, `rows 26-50`, `/positions` |
| When? | `excerpt.created_at`, `source.imported_at` |
| How? | `source.extraction_method`, `excerpt.created_via`, and for generated content `generation_id` → the full prompt and output |

The API returns this as a `provenance` block including a ready-made `citation`
string, and Markdown exports place that citation under every quotation.
