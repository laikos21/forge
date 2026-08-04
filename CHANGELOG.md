# Changelog

All notable changes to FORGE. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-08-03

First complete release. Every screen is functional against real data; there are
no placeholder controls.

### Added — import and extraction

- Inbox with drag-and-drop, file picker, batch import and paste-text import.
- Extractors for PDF (pypdf, per-page locators and document metadata), Markdown
  (section locators, YAML-ish front matter), plain text, CSV/TSV (delimiter and
  header sniffing, row-group locators), JSON and JSON Lines (record locators and
  pointers), transcripts (inline `0:00` stamps, WebVTT and SRT cues, speaker
  labels, wrapped-line joining), images (dimensions, format, EXIF, optional
  OCR), and pasted web articles (HTML tag stripping).
- Duplicate detection by SHA-256 of the original bytes and by normalised-text
  hash, with an explicit force-import override.
- Originals preserved in content-addressed storage; unparseable files become
  sources in an `error` state with their bytes intact rather than being lost.
- Review screen: detected metadata and entity candidates with stated confidence,
  keyword suggestions, extraction warnings and a text preview. Nothing detected
  is attached until confirmed.

### Added — library, search and knowledge

- Library with grid and table views; filters for type, status, tag, entity,
  author, language and date range (imported or published); facet counts;
  sorting; pagination; multi-select export.
- Source page: extracted-text reader with per-unit locators, selection-to-
  excerpt with automatic locator derivation, metadata editor, entity list, tag
  editor, relationship list, original-file access and Markdown export.
- Full-text search over sources, excerpts, knowledge objects, dossiers and
  entities (SQLite FTS5) with phrases, negation, prefix and column filters,
  highlighted snippets, grouping by source, provenance links and title
  suggestions. Diacritic-insensitive.
- Optional local semantic search behind an adapter, disabled by default.
- Knowledge objects: insights, trading rules, hypotheses, decisions, quotes and
  notes, each with per-kind lifecycles, confidence, review dates, tags and
  excerpt-backed evidence carrying a stance.
- Promotion of any excerpt into a knowledge object, keeping the excerpt as
  evidence and linking back to the source with `derived_from`.

### Added — dossiers, comparison, review

- Dossiers with overview, thesis, bull case, bear case, risks, open questions,
  timeline, claims with evidence, related entities, linked sources, excerpts and
  knowledge objects, tags and relationships.
- Dossier export to Markdown (evidence quoted inline with its citation) and to a
  zip bundle including linked sources and knowledge objects.
- Comparison workspace: any subjects across user-defined typed dimensions, exact
  decimal values, automatic ranking of numeric dimensions, Markdown export.
- Daily review: recent imports, unprocessed sources, unresolved hypotheses,
  recently modified dossiers, rules and decisions due within 14 days, loose-end
  counts, and suggested connections derived from shared tags or entities and
  labelled as deterministic metadata overlaps.

### Added — optional local intelligence

- Provider interface with Ollama as the one implementation; disabled by default.
- Six operations (summarise, extract entities, suggest topics, extract claims,
  generate questions, draft comparison), each with a deterministic fallback that
  reports itself as such.
- Generated output is badged in the interface and in exports, stays editable,
  never overwrites user content, and is recorded in a `generation` audit table
  with prompt and raw output.

### Added — data management

- SQLite with Alembic migrations, applied automatically at startup.
- Backup to a single zip (consistent database copy via SQLite's online backup
  API, portable JSON export, every original file, manifest with counts and
  checksum); restore with a safety backup, integrity validation and rollback.
- JSON export of every table, Markdown export for sources, knowledge objects,
  entities, dossiers and comparisons, and a selected-sources zip.
- Integrity check for dangling polymorphic references, missing originals and
  search-index drift.
- Demonstration data built from the shipped sample files through the real import
  pipeline, flagged `is_demo`, tagged `demo` and removable in one click.

### Added — interface

- Dark-first restrained design system (hand-written CSS, one accent colour),
  light theme, comfortable/compact density.
- Command palette (`Ctrl`/`Cmd`+`K`) with navigation, actions and live search;
  single-key navigation shortcuts; focus-trapped dialogs; skip link; ARIA roles
  on loading, empty and error states.
- Useful empty states on every screen, explicit loading and error states,
  responsive layouts down to a single column.

### Added — developer experience

- `bootstrap.ps1`, `run.ps1`, `test.ps1`, `build.ps1` for Windows PowerShell,
  plus `scripts/manage.py` for migrate / seed / reindex / backup / restore / info.
- 224 backend tests, 83 frontend tests, TypeScript type checking, and an
  end-to-end workflow smoke test covering import → review → search → excerpt →
  promote → dossier → export → backup → restore.

### Fixed during development

- **Transcript segmentation** merged unrelated turns into two blocks, destroying
  timestamp granularity; inline transcripts now produce one segment per
  timestamp and join hard-wrapped continuation lines.
- **Speaker detection** matched headlines such as `Episode 41: Managing…`;
  speaker labels are now restricted to 1–3 capitalised, digit-free words.
- **Image and PDF type checks** trusted the file extension when no magic number
  matched, so `evil.png` containing text passed validation. Binary formats are
  now verified against their own bytes only.
- **`formatBytes`** reported `2 KB` instead of `2.0 KB` because the unit index
  was compared against the wrong sentinel.
- **`formatDate`** rendered a calendar date one day early in negative UTC
  offsets by parsing `YYYY-MM-DD` as an instant; date-only values are now
  returned verbatim.
- **Dialog focus** landed on the close button rather than the first field,
  because a scoped CSS selector list only scoped its first entry.
- **`/api/settings/system` blocked for ~4 seconds** probing a non-existent
  Ollama instance on every Settings load. The provider is no longer contacted
  when the feature is disabled; an explicit "Re-check" performs the probe, and
  a test asserts no outbound call happens otherwise.
- **`build.ps1` aborted on a successful migration** because Windows PowerShell
  turns native-process stderr into an error record. Native invocations are now
  judged by exit code, and Alembic logs at WARNING.
- **Rules and decisions never appeared in the review queue** because only
  already-overdue items were selected; the queue now looks 14 days ahead and
  reports both `overdue_days` and `due_in_days`.

### Known limitations

See the end of `PRODUCT_DECISIONS.md` for scope deliberately left out, and
`TESTING.md` for what is deliberately not tested.
