# Product decisions

Decisions taken while building FORGE, the alternative that was rejected, and
what would change the call. Ordered roughly by how much they shape the product.

---

## 1. Detection proposes, the user disposes

**Decision.** Extraction and entity detection never write to a source's
user-visible fields. An import lands in `needs_review`; the review screen shows
what was detected, with a stated confidence, and the user confirms.

**Rejected.** Auto-attaching high-confidence entities and skipping review.

**Why.** A wrong ticker silently attached to a research note is worse than no
ticker: it corrupts every later filter and dossier suggestion, and it does so
invisibly. Bare uppercase tokens are reported as *low* confidence precisely
because `CEO` and `FED` look exactly like tickers.

**Escape hatch.** Settings → Import → "Skip the review step" for users who would
rather clean up later.

---

## 2. Every intelligent feature has a deterministic floor

**Decision.** Six operations (summarise, extract entities, suggest topics,
extract claims, generate questions, draft comparison) each have a non-model
implementation. The response states which one ran and why.

**Rejected.** Gating those features behind "install Ollama first".

**Why.** The brief requires usefulness with no API key and no cloud service. A
feature that only exists for users who installed a 5 GB model is a feature most
users never see. The fallbacks are also *honest by construction*: the extractive
summary copies sentences verbatim, so it can be quoted; claim extraction returns
sentences containing claim-like language rather than an interpretation.

**Exception, stated in the UI.** Comparison drafting has no useful deterministic
equivalent, so it returns an empty grid rather than guessing. Inventing cell
values would be the one place a fallback could fabricate content.

---

## 3. Suggested connections are metadata overlaps, never inferences

**Decision.** The review screen's suggestions come from shared tags and shared
entities between objects that are not yet linked. Each one states its exact
basis ("Both tagged ai-infrastructure, power"), is labelled
`deterministic_metadata_overlap`, and the screen carries a disclaimer.

**Rejected.** Embedding-similarity "related items" presented without
qualification.

**Why.** The brief is explicit: do not present deterministic suggestions as
AI-generated conclusions. The inverse matters too — presenting a similarity
score as a *finding* invites the user to treat coincidence as evidence.

---

## 4. Generated content is quarantined, not merged

**Decision.** LLM endpoints return drafts. They never write to a user-facing
field. The client posts the edited draft back through the normal create/update
endpoints, which stamp `origin='generated'` and `generated_by`. Every call is
recorded in the `generation` table with its prompt and raw output. The badge
follows the object into the UI and into Markdown exports.

**Rejected.** Writing a generated summary straight onto `source.summary`.

**Why.** "Never silently overwrite user content" and "never treated as verified
fact" are only real if generated text is distinguishable from the user's own
text *forever*, including six months later in an exported file.

**Concrete instance.** The dossier "find gaps" action *appends* to open
questions and says so; it cannot replace what is there.

---

## 5. Knowledge objects share one table

**Decision.** Insight, rule, hypothesis, decision, quote and note are one table
with a `kind` discriminator and per-kind status vocabularies.

**Rejected.** Six tables, or single-table inheritance with six ORM subclasses.

**Why.** They differ in *lifecycle*, not in structure. Six tables would multiply
every linking table and every query by six. The cost is that kind-specific
fields live in `data_json` rather than typed columns — acceptable while those
fields are few and never queried.

**What would change it.** If a kind needed to be queried on its own structured
fields (say, decisions filtered by position size), that kind earns its own table.

---

## 6. Polymorphic references instead of twenty join tables

**Decision.** Tags, dossier items, collection items, comparison subjects and
links address objects as `(target_type, target_id)`.

**Rejected.** A typed join table per (container, target) pair.

**Why.** Roughly twenty tables and twenty code paths for identical behaviour.

**The price, and how it is paid.** SQLite cannot enforce these as foreign keys,
so integrity is enforced in the service layer and *verified* by
`GET /api/maintenance/integrity`, which is surfaced in Settings and asserted by
the end-to-end test. This is the largest deliberate correctness compromise in
the system, which is why it has a dedicated check.

---

## 7. The full-text index is maintained by the application

**Decision.** `services/indexer.py` writes the FTS5 rows; no SQL triggers.

**Rejected.** Trigger-maintained index (the usual FTS5 pattern).

**Why.** What FORGE indexes is a *composition*: a dossier's overview + thesis +
bull + bear + risks; a source's text + author + detected tickers. Triggers only
see raw column values. Keeping composition in Python makes it explicit,
testable, and rebuildable.

**The price.** A new write path must remember to call the indexer. Mitigated by
the integrity check comparing index entries against indexable objects, and by
`POST /api/search/reindex` being a one-click fix.

---

## 8. Fictional demonstration data

**Decision.** The sample corpus is built around **Helios Semiconductor (HLSX)**,
an invented company, with invented figures. Every sample file says so in its
first lines, every seeded row carries `is_demo`, everything is tagged `demo`,
and one click removes it all.

**Rejected.** A realistic dossier on a real ticker with plausible numbers.

**Why.** Realistic-looking financial figures attached to a real company are
fabricated financial claims. They would be indistinguishable from research after
a few weeks, they would be exported into Markdown files that outlive the demo,
and they could be acted on. An invented company keeps the demo just as useful as
a worked example while making it impossible to mistake for data.

---

## 9. Seed data is imported through the real pipeline

**Decision.** `app/seed.py` runs the sample files through `ingest.ingest_bytes`
and `ingest_text`, then attaches excerpts by *searching the extracted text* for
verbatim phrases — raising if a phrase is not found.

**Rejected.** Inserting pre-baked source rows with hand-written text.

**Why.** It guarantees the demo exercises the same code path a user's own file
takes, and that every demo excerpt quotes text that genuinely exists at the
offsets recorded. If extraction regresses, the seed breaks — which is the point.

---

## 10. The URL owns list state

**Decision.** Library filters, search queries and result grouping live in the
query string, parsed by `lib/filters.ts`.

**Rejected.** Component state or a client store.

**Why.** Research is comparative: two windows side by side, a filtered view kept
for later, the back button behaving. Serialisation is pure and unit-tested.

---

## 11. Highlighting via control characters, never HTML

**Decision.** FTS5 `snippet()` wraps matches in U+001F/U+001E. The frontend
splits on them and renders `<mark>` elements.

**Rejected.** Returning `<b>` tags and using `dangerouslySetInnerHTML`.

**Why.** The indexed text is user-supplied content from arbitrary PDFs and web
pages. Any path that parses it as HTML is an injection vector. Control
characters cannot occur in extracted text and cannot be interpreted as markup.
The same reasoning produced a hand-written Markdown renderer that emits React
elements instead of HTML strings.

---

## 12. Python 3.13 rather than the suggested 3.12

**Decision.** Require 3.11+, develop on 3.13.13 (what this machine has).

**Why.** Nothing in the stack needs 3.12 specifically, and the bundled SQLite in
newer python.org builds is more current — 3.13.13 ships SQLite 3.50.4 with FTS5,
which is the actual dependency. `bootstrap.ps1` verifies FTS5 rather than
trusting a version number.

---

## 13. No state-management library, no CSS framework

**Decision.** `useAsync` (~40 lines) covers every screen's loading/error/data
pattern. Styling is a hand-written CSS design system with custom properties.

**Rejected.** React Query + Tailwind (or shadcn/ui).

**Why.** Every screen is a fresh read of a local database — there is no
cache-invalidation problem to solve, and a stale cache would be a *bug* in an app
whose whole point is that the data is local and current. For styling, a
restrained dark-first interface with one accent colour is easier to keep
coherent as CSS than as thousands of utility classes, and it keeps the build
dependency-free. Total production bundle: 374 KB JS, 21 KB CSS.

**What would change it.** Multi-user or remote data would make React Query the
right call immediately.

---

## 14. Backups are one zip, restores are reversible

**Decision.** A backup contains `forge.db` (via SQLite's online backup API),
`export.json` (the same data as portable JSON), every original file, and a
manifest with counts and a database checksum. Restore moves the current state
aside first, validates the incoming database with `PRAGMA integrity_check` and
a required-table check, and rolls back on any failure.

**Rejected.** Copying `forge.db` directly (breaks under WAL) or exporting JSON
only (loses the originals).

**Why.** A backup nobody trusts is not a backup. `export.json` also means the
data is readable without FORGE, or without SQLite.

---

## 15. Windows-first, and defensive about this machine

**Decision.** The PowerShell scripts repair their own copy of `PATH` at startup,
and treat native-process stderr as informational, judging success by exit code.

**Why.** Both were real failures here. A stray `"` in the machine `PATH`
(`C:\Program Files\Cloudflare\Cloudflare WARP"`) makes `cmd.exe` stop resolving
every entry after it, which surfaced as npm reporting `'node' is not
recognized`. Separately, Windows PowerShell turns any stderr output from a
native command into an error record, so an informational alembic log line
aborted `build.ps1`. Both are fixed inside the scripts' own process; the user's
system settings are never modified.

---

## 16. Scope deliberately left out

* **Browser extension / web clipper.** Pasting is the supported path; a
  clipper is a separate product surface.
* **Automatic fetching of URLs.** Would make internet access load-bearing.
  A URL is stored as metadata; the text is pasted.
* **PDF page images / annotation overlay.** Requires a rendering engine and
  turns the reader into a viewer. Text plus page locators covers citation.
* **Multi-user, auth, sharing.** Local-first, single-user. Adding auth would
  imply a threat model this design does not have.
* **Scheduled jobs / watched folders.** Import is a deliberate act; a watcher
  would fill the inbox with material nobody chose to keep.
