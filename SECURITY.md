# Security

## Threat model

FORGE is a single-user, local-first application. It binds to `127.0.0.1`, has no
authentication, no multi-tenancy and no remote data. The realistic threats are
therefore not "an attacker on the internet" but:

1. **Malicious or malformed input files.** You import PDFs, CSVs, JSON and
   images from sources you do not control. A crafted file must not escape the
   storage directory, exhaust memory, or execute anything.
2. **Untrusted content rendered in the interface.** Extracted text from an
   arbitrary web page or PDF is displayed constantly. It must never be
   interpreted as markup or code.
3. **Data loss.** Losing years of research to a bad restore or a failed write is
   the worst realistic outcome.
4. **Unintended network egress.** The product's promise is that nothing leaves
   the machine.

What is explicitly **out of scope**: an attacker with local access to your user
account (they can read `data\forge.db` directly), and hostile users of the same
instance (there is only one user).

## 1. Upload handling

**Size limits.** `FORGE_MAX_UPLOAD_MB` (default 128) per file,
`FORGE_MAX_BATCH_FILES` (default 50) per request, 8 million characters per
pasted text. Enforced before any parsing.

**Type verification by content, not extension.** `lib/files.detect_magic`
inspects the leading bytes. A file claiming to be `.pdf` without `%PDF-` is
rejected; a file claiming to be `.png` without a recognised image signature is
rejected. The extension is only a fallback for formats that have no magic
number (text, CSV, JSON, Markdown), where the content is parsed as text anyway.

**Parser hardening.** Every extractor is wrapped: any exception becomes an
`ExtractionError`, which becomes a source in the `error` state with the original
bytes preserved and the message shown to the user. A malformed file cannot crash
a request or abort a batch. Row and record caps (20 000 CSV rows, 2 000 JSON
records, 6 levels of nesting) bound memory on pathological input.

**Encrypted PDFs.** An empty owner password is attempted (common for
"protected" documents) and reported in the warnings; anything else is refused
rather than brute-forced.

**No archive expansion.** Zip, tar and Office containers are not accepted as
import formats, so there is no zip-bomb surface on import.

## 2. Path safety

Client filenames are **never** used to build a path. They are sanitised
(`lib/files.sanitize_filename`: directory components stripped, unsafe characters
replaced, Windows reserved names like `CON` prefixed) and kept only as display
metadata.

Storage is content-addressed: `data\files\<sha256[:2]>\<sha256><ext>`, where the
extension is only accepted if it matches `\.[A-Za-z0-9]{1,8}`. Path traversal is
structurally impossible — the path is derived from a hash, not from input.

Every read of a stored blob goes through `resolve_within(root, relative)`, which
resolves the candidate and refuses anything that is not under the storage root.

Backup archives are validated before extraction: any member whose normalised
path is absolute or contains `..` aborts the restore
(`test_path_traversal_in_archive_is_refused`).

## 3. Rendering untrusted content

**No `dangerouslySetInnerHTML` anywhere in the frontend.**

* Search highlighting uses control characters (U+001F/U+001E) that the frontend
  splits into plain-text segments and renders as `<mark>` elements. Extracted
  text cannot contain them and cannot introduce markup.
* Markdown is rendered by a hand-written parser (`lib/markdown.tsx`) that emits
  React elements directly. There is no HTML string in the path, so no
  sanitiser to get wrong. Tested with `<img src=x onerror=...>` input, which
  renders as visible text.
* HTML pasted as a web article is stripped server-side with a tag-aware parser
  that discards `<script>`, `<style>` and `<svg>` content, and the source is
  flagged with a warning that markup was removed.
* Original files are served with `X-Content-Type-Options: nosniff` and their
  recorded MIME type. PDFs and images open in the browser's own viewer;
  everything else downloads.

## 4. Injection

**SQL.** All queries go through SQLAlchemy with bound parameters. The raw SQL
that exists (the FTS5 statements) uses named parameters exclusively; the only
interpolated values are internal column-name constants.

**Full-text query syntax.** The user's search string never reaches SQLite.
`search.parse_query` tokenises it and re-quotes every term, so `NEAR(`, an
unbalanced `"`, or `^` produce zero results rather than an FTS5 syntax error or
an unintended query.

**Request bodies.** Pydantic models use `extra="forbid"`, so an unexpected field
is a 422 rather than a silently ignored value. Enumerated values, lifecycle
statuses and relation names are validated against closed vocabularies.

## 5. Network egress

FORGE makes exactly two kinds of outbound request, both to a user-configured
local address and both optional:

| Call | When |
| --- | --- |
| `GET {ollama}/api/tags` | Provider status, only when local LLM is enabled or the user presses "Re-check" |
| `POST {ollama}/api/generate`, `/api/embeddings` | Only when the user runs an operation with the feature enabled |

Both default to `http://127.0.0.1:11434`. With local intelligence disabled —
the default — the application makes **no outbound connections at all**, and this
is enforced by a test that patches `httpx` to raise and asserts the status
endpoints still succeed.

No telemetry, no update checks, no analytics, no fonts or scripts from a CDN.
The frontend bundle contains no external references.

## 6. Data durability

* SQLite runs in WAL mode with `synchronous=NORMAL` and foreign keys on.
* Blobs are written to a `.part` file and atomically replaced.
* Backups use SQLite's online backup API, so a backup taken while the
  application is running is consistent.
* Restore writes a safety backup first, validates the incoming database with
  `PRAGMA integrity_check` and a required-table check, and rolls the previous
  database back if any step fails.
* Deleting a source removes its blob only when no other source shares the same
  content hash.

## 7. Secrets

FORGE has none. There is no API key, no token, no password, and no field that
stores one. If you enable a local model provider, its base URL is the only
credential-shaped value in the system, and it is a `localhost` address.

## Reporting

This is a personal, local application. If you find a defect with security
implications, note it in `CHANGELOG.md` and fix it — there is no external
disclosure process, and no user other than you is exposed.
