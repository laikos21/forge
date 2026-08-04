# FORGE

**A local-first personal research intelligence system.**

FORGE turns an unstructured pile of PDFs, transcripts, screenshots, notes and
spreadsheets into a traceable, searchable, interconnected knowledge base. Every
derived insight keeps a link back to the exact page, timestamp, section or row
it came from.

It runs entirely on your machine. No account, no API key, no cloud service, no
internet connection — SQLite for storage and full-text search, the local
filesystem for your original files, and an *optional* local model provider for
accessory features that always have a deterministic fallback.

---

## Requirements

| Requirement | Version | Notes |
| --- | --- | --- |
| Windows | 10 / 11 | Developed and verified on Windows 11 Pro 26100 |
| Python | 3.11+ | 3.13 recommended; must be the python.org build (needs SQLite FTS5) |
| Node.js | 20+ | 24 LTS recommended |
| Disk | ~400 MB | Dependencies, plus whatever your own material needs |

Optional: [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) for
screenshot text, and [Ollama](https://ollama.com) for local LLM assistance.
Neither is required and neither is used unless you enable it.

## Install (Windows, PowerShell)

```powershell
cd "C:\Users\Agu\Documents\Claude Local Session\forge"
.\bootstrap.ps1
```

`bootstrap.ps1` verifies Python, Node and SQLite FTS5, creates
`backend\.venv`, installs both dependency sets, generates the sample documents,
applies the database migrations and loads the demonstration data.

If PowerShell refuses to run the scripts:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

To skip the demonstration content:

```powershell
.\bootstrap.ps1 -SkipDemo
```

## Run

```powershell
.\run.ps1
```

Opens <http://127.0.0.1:5173> with the API on <http://127.0.0.1:8000> (hot
reload on both). Press <kbd>Ctrl</kbd>+<kbd>C</kbd> to stop both processes.

Single-port production mode (builds the frontend, then serves everything from
the API):

```powershell
.\run.ps1 -Prod
```

Other options: `-Port 8080`, `-FrontendPort 5180`, `-NoBrowser`.

## Test

```powershell
.\test.ps1
```

Runs the backend suite (pytest), frontend type checking (tsc) and the frontend
suite (vitest). Subsets and filters:

```powershell
.\test.ps1 -Backend -Filter duplicate
.\test.ps1 -Frontend
```

## Build

```powershell
.\build.ps1
```

Runs the tests, byte-compiles the backend, applies migrations, type-checks and
builds `frontend\dist`. Use `-SkipTests` to build without re-running them.

## Maintenance CLI

```powershell
backend\.venv\Scripts\python.exe scripts\manage.py info
backend\.venv\Scripts\python.exe scripts\manage.py seed --reset
backend\.venv\Scripts\python.exe scripts\manage.py backup --label before-cleanup
backend\.venv\Scripts\python.exe scripts\manage.py restore data\backups\forge-backup-20260803-120000.zip
backend\.venv\Scripts\python.exe scripts\manage.py reindex
backend\.venv\Scripts\python.exe scripts\manage.py demo-clear
```

---

## Where your data lives

```
data\
  forge.db          SQLite database (schema, text, search index)
  files\            original files, content-addressed by SHA-256
  backups\          backup archives created from Settings or the CLI
  tmp\              staging area used during backup and restore
```

Move it elsewhere by setting `FORGE_DATA_DIR` before starting:

```powershell
$env:FORGE_DATA_DIR = "D:\forge-data"
.\run.ps1
```

Other environment variables: `FORGE_MAX_UPLOAD_MB` (default 128),
`FORGE_MAX_BATCH_FILES` (50), `FORGE_AUTO_MIGRATE` (true),
`FORGE_SERVE_FRONTEND` (true), `FORGE_OLLAMA_BASE_URL`.

`data\` is git-ignored. It is yours, and nothing in FORGE sends it anywhere.

---

## The workflow

1. **Inbox** — drop files or paste text. FORGE extracts and normalises the
   content, records the original bytes, and detects metadata and entities.
   Duplicates are caught by SHA-256 (exact) and by normalised-text hash
   (re-wrapped copies of the same article).
2. **Review** — confirm the title, author, date, language, tags and the detected
   entities. Nothing detected is attached until you confirm it.
3. **Library** — grid or table, filtered by type, status, tag, entity, author or
   date. The source page shows the extracted text with its structural units,
   the original file, the metadata editor and every excerpt taken from it.
4. **Excerpt** — select any passage in the reader to quote it. The locator
   (page, timestamp, section, row, JSON pointer) is derived from the unit the
   selection starts in.
5. **Knowledge** — promote an excerpt into an insight, trading rule, hypothesis,
   decision, quote or note. The excerpt stays attached as evidence, and the new
   object is linked back to the source with `derived_from`.
6. **Dossier** — a research workspace for one subject with an overview, thesis,
   bull case, bear case, risks, open questions, a timeline, claims with
   evidence, related entities and linked sources. Exports to Markdown or to a
   zip bundle with every linked source.
7. **Compare** — put subjects side by side across dimensions you define.
8. **Review** — what arrived, what is unfinished, what overlaps.

## Search

SQLite FTS5, always available:

| Query | Meaning |
| --- | --- |
| `breakout base` | both words must appear |
| `"volume dry up"` | exact phrase |
| `breakout -crypto` | exclude a word |
| `semis*` | prefix match |
| `title:nvidia` | match in the title only |

Results can be grouped by source, carry highlighted snippets and link back to
their provenance. Diacritics are folded, so `expansion` matches `expansión`.

Semantic search is an **optional adapter** (Ollama embeddings, cosine
similarity over a local vector table). It is disabled by default; full-text
search is unaffected whether it is on or off.

## Optional local intelligence

Enable it in **Settings → Local intelligence** with Ollama running locally:

```powershell
winget install Ollama.Ollama
ollama pull llama3.1:8b
```

Available operations: summarise, extract entities, suggest topics, extract
claims, generate open questions, draft comparison cells.

Every generated result is **visibly marked as generated**, keeps its source
references, stays editable, never overwrites your text, and is never treated as
verified fact. Every call is recorded in a `generation` audit table. With no
model installed, each operation falls back to a deterministic equivalent and
says so — extractive summaries copy sentences verbatim, entity extraction uses
pattern matching, question generation reports structural gaps.

## Keyboard

<kbd>Ctrl</kbd>+<kbd>K</kbd> command palette · <kbd>/</kbd> search ·
<kbd>g</kbd> home · <kbd>i</kbd> inbox · <kbd>l</kbd> library ·
<kbd>d</kbd> dossiers · <kbd>r</kbd> review · <kbd>Esc</kbd> close dialog

## Backup and restore

Settings → Backups, or the CLI. A backup is a single `.zip` containing a
consistent copy of the database (taken with SQLite's online backup API), every
stored original, and a portable `export.json`. Restoring writes a safety backup
of the current state first and rolls back if anything fails.

---

## Documentation

| File | What it covers |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Layers, request flow, the tradeoffs behind them |
| [DATA_MODEL.md](DATA_MODEL.md) | Every table, why it exists, provenance rules |
| [PRODUCT_DECISIONS.md](PRODUCT_DECISIONS.md) | Decisions taken, alternatives rejected |
| [TESTING.md](TESTING.md) | What is tested, how to run it, what is deliberately not |
| [SECURITY.md](SECURITY.md) | Threat model, upload validation, path safety |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |

## Troubleshooting

**`'node' is not recognized` during bootstrap.** This machine's `PATH` contains
an unbalanced double quote (`C:\Program Files\Cloudflare\Cloudflare WARP"`),
which makes `cmd.exe` stop resolving every entry after it. The FORGE scripts
repair their own copy of `PATH` at startup and print a warning; your system
settings are left untouched. To fix it permanently, edit the system `PATH` and
remove the stray `"`.

**Port already in use.** `.\run.ps1 -Port 8010 -FrontendPort 5180`.

**"Cannot reach the FORGE backend" in the interface.** The API process stopped.
Check the terminal that `run.ps1` is using, then restart it.

**Search returns nothing after restoring a backup.** Settings → Data and
maintenance → Rebuild search index.

**A PDF imported with no text.** It is a scan. FORGE keeps the original and
flags the source; install Tesseract, enable OCR in Settings, then use Reprocess
on the source page.
