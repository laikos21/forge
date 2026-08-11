# AGENTS.md — working brief for FORGE

You are picking up a finished, working project. Read this before touching
anything. It is written for an agent with no memory of how FORGE was built.

*(This file is named `AGENTS.md` because Codex loads it automatically from the
repository root. If your tool does not, read it manually first.)*

---

## 1. Status

**FORGE 0.1.0 — complete and verified.** Not a prototype, not a scaffold.
Every screen works against real data; there are no placeholder controls, no
stubs, no unimplemented handlers.

| | |
| --- | --- |
| Repository | <https://github.com/laikos21/forge> (public) |
| Local path (owner's machine) | `C:\Users\Agu\Documents\Claude Local Session\forge` |
| Baseline commit | `00a1a0c` — "FORGE 0.1.0 - local-first research intelligence system" |
| Backend tests | 224 passing |
| Frontend tests | 83 passing |
| Type check | clean |
| Production build | succeeds — 374 KB JS, 21 KB CSS |

**Owner:** Agu — Santa Fe, Argentina. Procurement at a hospital; swing trader
(momentum, 1 day–3 months); self-taught developer. Writes to him in Spanish;
all project documentation, code and commits stay in English.

**What FORGE is.** A local-first personal research intelligence system. It
turns PDFs, transcripts, screenshots, notes and tabular files into a traceable,
searchable, interconnected knowledge base. Every derived insight keeps a link
back to the exact page, timestamp, section or row it came from.

**The constraint that shapes every decision:** it must be fully useful with no
paid API, no cloud service, no account and no API key, running locally on
Windows 11. Do not introduce anything that violates this. If a change would
make a network call, a cloud service or a key *required* for a core workflow,
the change is wrong — find another way.

---

## 2. Read these first, in this order

1. `README.md` — what it does and how to run it.
2. `PRODUCT_DECISIONS.md` — **the most important file for you.** Sixteen
   decisions with the alternative that was rejected and why. If you are about to
   "improve" something, check here first: several obvious-looking improvements
   were considered and deliberately not made.
3. `ARCHITECTURE.md` — layering and the reasoning behind it.
4. `DATA_MODEL.md` — 25 tables, the provenance guarantee, the polymorphic
   reference trade-off.
5. `TESTING.md` — what is covered and what is deliberately not.
6. `SECURITY.md` — threat model (malicious input files, untrusted content
   rendering, data loss, unintended egress).
7. `CHANGELOG.md` — in particular **"Fixed during development"**: eight real
   bugs already hit and fixed. Do not reintroduce them (see §8).

---

## 3. Environment — read this before running anything

The developer experience is **Windows PowerShell**. If you are running in a
Linux container (Codex cloud), the `.ps1` scripts will not run. Use the
equivalents below — they do exactly the same thing.

### Toolchain

Python 3.11+ (built and verified on 3.13.13) and Node 20+ (verified on 24.18).
Python **must** have SQLite FTS5 compiled in — that is the actual dependency,
not a version number. Check it:

```bash
python -c "import sqlite3;c=sqlite3.connect(':memory:');c.execute('CREATE VIRTUAL TABLE t USING fts5(a)');print('FTS5 ok')"
```

### Cold start on Linux / macOS

`data/` is **not** in the repository (it is the owner's knowledge base). A fresh
clone therefore has no database. `samples/` **is** committed, so you do not need
to regenerate the fixtures.

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -e "backend[dev]"
backend/.venv/bin/python scripts/manage.py migrate
backend/.venv/bin/python scripts/manage.py seed
cd frontend && npm ci && cd ..
```

Run it:

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000   # API on :8000
cd frontend && npm run dev                                           # UI  on :5173
```

### Cold start on Windows (the owner's machine)

```powershell
.\bootstrap.ps1
.\run.ps1
```

### Test and build — Linux / macOS

```bash
(cd backend  && .venv/bin/python -m pytest -q)
(cd frontend && npx tsc --noEmit -p tsconfig.app.json && npx vitest run && npx vite build)
```

### Test and build — Windows

```powershell
.\test.ps1
.\build.ps1
```

---

## 4. Machine-specific traps (Windows only)

These are real failures already hit on the owner's machine. The scripts work
around them; do not "clean up" the workarounds.

1. **A stray quote in the system `PATH`.** The entry
   `C:\Program Files\Cloudflare\Cloudflare WARP"` has an unbalanced `"`, which
   makes `cmd.exe` stop resolving every entry after it. Symptom: npm reports
   `'node' is not recognized` even though Node is installed and on `PATH`.
   `scripts/common.ps1 → Repair-PathVariable` strips stray quotes from the
   script's own copy of `PATH` and warns. It never modifies system settings.
2. **Windows PowerShell treats native-process stderr as an error record.** With
   `$ErrorActionPreference = 'Stop'`, one informational log line from Alembic
   aborted `build.ps1`. `Invoke-Native` relaxes the preference and judges
   success by exit code only. Alembic logs at WARNING for the same reason.
3. **npm blocks `esbuild`'s postinstall** ("allow-scripts"). Harmless — the
   platform binary at `frontend/node_modules/@esbuild/win32-x64/esbuild.exe`
   is installed by the optional dependency and works. Do not run
   `npm approve-scripts` to "fix" it.
4. **The provider probe.** Use `127.0.0.1`, never `localhost`, for the Ollama
   base URL. On Windows `localhost` resolves to `::1` first and a dead IPv6
   attempt has to time out before IPv4 is tried — four seconds of dead wait.

---

## 5. Map

```
backend/app/
  api/          HTTP only: parse, call a service, serialise. No business logic.
  services/     All rules. Takes a Session, never sees a Request.
  lib/          Pure functions. No DB, no framework.
  models.py     ORM only.  schemas.py  Request validation (extra="forbid").
  domain.py     Every closed vocabulary lives here. Start here for any new value.
  seed.py       Demo data, built by running the real import pipeline.
backend/tests/  9 files, mirrors the layering.
frontend/src/
  lib/          api.ts (the only fetch), format, filters, highlight, markdown, hooks.
  components/   Presentation primitives. No data fetching.
  pages/        13 screens.
scripts/        manage.py CLI, make_samples.py, minipdf.py, common.ps1
samples/        Committed fixtures. Used by BOTH the seed and the tests.
```

**The layering is load-bearing.** Extraction, search-query parsing and
provenance are tested directly against `lib/` and `services/` with no HTTP
involved, which is why 224 tests run in ~40 s. Putting business logic in a
route or in a React component breaks that.

---

## 6. Invariants — do not break these

1. **Excerpt offsets address real characters.** The normalized text of a source
   *is* its extracted units joined by `\n\n`, and
   `extraction/base.assemble()` produces both in one pass. Every extractor test
   asserts `text[unit.char_start:unit.char_end] == unit.text`. If you add a
   format, add that assertion.
2. **Detection proposes, the user disposes.** Extraction and entity detection
   never write to a source's user-visible fields. Imports land in
   `needs_review`; the user confirms. A wrong ticker silently attached is worse
   than no ticker.
3. **Every intelligent feature has a deterministic floor.** Six operations in
   `services/llm/operations.py`, each with a non-model fallback that reports
   itself as such. New operations follow the same shape. The one documented
   exception is comparison drafting, which returns an empty grid rather than
   guessing.
4. **Generated content is quarantined, never merged.** LLM endpoints return
   drafts. The client posts the edited draft back through the normal
   create/update endpoints, which stamp `origin='generated'` and `generated_by`.
   Every call is audited in the `generation` table. The badge follows the object
   into the UI and into Markdown exports.
5. **No network when local intelligence is disabled.** Enforced by a test that
   patches `httpx` to raise and asserts the status endpoints still succeed.
   Do not add telemetry, update checks, CDN fonts or analytics.
6. **The user's search string never reaches SQLite.** `search.parse_query`
   tokenises and re-quotes every term. A stray `"` or `NEAR(` must produce zero
   results, never a 500.
7. **No `dangerouslySetInnerHTML`, ever.** Highlighting uses U+001F/U+001E
   control characters split into plain-text segments; Markdown is a hand-written
   parser emitting React elements. Indexed text comes from arbitrary PDFs and web
   pages — any path that parses it as HTML is an injection vector.
8. **The FTS index is maintained by the application.** Every write path that
   touches an indexable object must call `services/indexer.py`. Verified by
   `GET /api/maintenance/integrity`, which compares index entries against
   indexable objects.
9. **Polymorphic references are validated in the service layer.** SQLite cannot
   enforce `(target_type, target_id)` as a foreign key. Any service that creates
   such a row checks existence via `services/refs.py` and cleans up on delete.
10. **Demo data stays fictional.** Helios Semiconductor (HLSX), Voltaris (VLTR),
    Coronex (CRNX) are invented, and every sample file says so. Do not swap in a
    real ticker with plausible figures — that is fabricating financial claims
    that would outlive the demo in exported Markdown.

---

## 7. How to know you did not break anything

```bash
(cd backend  && .venv/bin/python -m pytest -q)                   # expect 224 passed
(cd frontend && npx tsc --noEmit -p tsconfig.app.json)           # expect no output
(cd frontend && npx vitest run)                                  # expect 83 passed
(cd frontend && npx vite build)                                  # expect ✓ built
```

Then, against a running instance with demo data loaded:

```bash
curl -s localhost:8000/api/maintenance/integrity | python -m json.tool
```

Expect `"healthy": true`, `dangling_references: []`, `missing_original_files: []`
and `index.entries == index.expected` (33 with the demo data).

The end-to-end test `backend/tests/test_e2e_workflow.py` walks the whole
definition of done: import → review → search → excerpt → promote → dossier →
export → backup → destroy → restore. **If you change anything structural, that
test is the one that tells you the truth.**

---

## 8. Bugs already fixed — do not reintroduce

From `CHANGELOG.md`, each one hit during the build:

| Trap | What went wrong |
| --- | --- |
| Transcript merging | Merging short segments destroyed timestamp granularity. Inline transcripts now produce one segment per timestamp; only cue formats merge. |
| Speaker regex | `Episode 41: Managing…` was parsed as a speaker. Labels are now 1–3 capitalised, digit-free words. |
| Type checks | `sniff_mime` fell back to the extension, so `evil.png` containing text passed. Binary formats use `detect_magic` (bytes only). |
| `formatBytes` | Compared the unit index against the wrong sentinel → `2 KB` instead of `2.0 KB`. |
| `formatDate` | Parsed `YYYY-MM-DD` as an instant → one day early in negative UTC offsets. Date-only values are returned verbatim. |
| Dialog focus | `.modal__body a, b` only scopes the first selector; focus landed on the close button. Each part needs the prefix. |
| Provider probe | `/api/settings/system` blocked ~4 s probing a non-existent Ollama on every load. Never probe when the feature is disabled. |
| Review horizon | Only overdue rules appeared, so the queue looked permanently empty. It now looks 14 days ahead. |

---

## 9. Backlog

Nothing here is required — 0.1.0 is complete. These are the honest next steps,
strongest first. Each names its entry point.

### Worth doing

1. **Excerpt highlighting inside the reader.** The source page shows extracted
   text and lists excerpts separately; the excerpts are not marked *in* the text.
   Offsets already exist (`excerpt.char_start/char_end`) and
   `lib/highlight.ts → highlightTerms` already returns segments.
   Entry point: `frontend/src/pages/SourcePage.tsx`, the `reader__unit` loop.
2. **Deep-link to an excerpt.** `/library/:id?excerpt=<id>` scrolling to and
   flashing the passage. Search results for excerpts currently land on the
   source page with no position. Entry points: `SearchPage.tsx → hitLink`,
   `SourcePage.tsx`.
3. **Down-weight ubiquitous tags in review suggestions.** Every demo object
   shares the `demo` tag, so it inflates every overlap score. A tag on >40% of
   objects carries no information. Entry point:
   `backend/app/services/review.py → suggested_connections`.
4. **Bulk actions in the library.** Selection exists (used for export); tagging
   and deleting a selection do not. Entry point: `LibraryPage.tsx`.
5. **Dossier claim reordering.** `position` is stored and honoured but nothing
   sets it after creation. Needs drag-and-drop or up/down controls.
   Entry points: `routes_dossiers.py → update_claim` (already accepts
   `position`), `DossierPage.tsx`.

### Larger, only if the need is real

6. **Code-split the frontend.** One 374 KB chunk. Fine locally; route-level
   `React.lazy` would halve first paint if it ever felt slow.
7. **Real vector index for semantic search.** Currently a linear cosine scan in
   Python — fine for thousands of objects. Beyond that, `services/semantic.py`
   is the only file that changes. That is why the adapter exists.
8. **Better PDF extraction.** pypdf is pure-Python (no build tools on Windows)
   and weaker on multi-column layouts and tables. pdfium would improve quality
   at the cost of a native dependency. Weigh against the "works after
   `bootstrap.ps1` on any Windows box" promise.
9. **Browser-driven E2E.** The smoke test is API-level on purpose: Playwright
   needs a browser download, and network-free operation is the product promise.
   If added, keep it optional and out of the default `test.ps1` path.

### Deliberately out of scope

Browser extension / web clipper; automatic URL fetching (would make internet
access load-bearing); PDF page images and annotation overlay; multi-user, auth
and sharing; scheduled jobs and watched folders. Reasons in
`PRODUCT_DECISIONS.md §16`.

---

## 10. Conventions

- **Language.** Chat with Agu in Spanish. Code, comments, documentation, commit
  messages and UI copy in English.
- **Commits.** Imperative subject under ~70 chars, blank line, body explaining
  *why*. Update `CHANGELOG.md` in the same commit as a user-visible change.
- **Scope.** Small, reversible, verifiable changes. Understand the current
  system before touching it; modify existing files before creating new ones.
  Preserve existing structure, naming and style. No scope creep — optional
  extras go in a separate note, not into the change.
- **Never infer missing data.** In this codebase and in Agu's documents alike:
  flag the gap explicitly instead of filling it in.
- **Tests.** New behaviour ships with a test. Put logic in `lib/` or `services/`
  and test it there; reserve component tests for what a user actually does.
- **Docs.** A change that alters behaviour updates the relevant doc in the same
  commit. `PRODUCT_DECISIONS.md` gets a new entry when a real alternative was
  rejected.
- **Never commit `data/`.** It is the owner's knowledge base and is gitignored.
- **Binary fixtures.** `.gitattributes` forces `binary` for PDFs and images.
  The sample PDF is generated by a hand-written writer whose xref table stores
  byte offsets — one LF→CRLF rewrite corrupts it, and git's heuristic does not
  detect it as binary. Do not relax those rules.

---

## 11. If something is broken on arrival

| Symptom | Fix |
| --- | --- |
| No database / empty app | `python scripts/manage.py migrate` then `seed` |
| Search returns nothing | `python scripts/manage.py reindex` |
| `'node' is not recognized` (Windows) | The `PATH` quote — see §4.1 |
| Port in use | `.\run.ps1 -Port 8010 -FrontendPort 5180` |
| PDF imported with no text | It is a scan. Install Tesseract, enable OCR in Settings, use Reprocess. |
| Tests touch real data | They cannot — `conftest.py` points `FORGE_DATA_DIR` at a fresh `tmp_path` per test. |
