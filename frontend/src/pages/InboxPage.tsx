import { useCallback, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useToast } from '../components/Toasts'
import { Badge, EmptyState, ErrorState, Field, Loading, Section } from '../components/ui'
import { api } from '../lib/api'
import { formatBytes, formatNumber, parseTagInput, relativeTime, SOURCE_KIND_LABELS, titleCase } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { ImportResponse, SourceKind } from '../lib/types'

const PASTE_KINDS: Array<{ value: string; label: string; hint: string }> = [
  { value: '', label: 'Detect automatically', hint: 'Timestamps are detected as a transcript.' },
  { value: 'note', label: 'Note', hint: 'Your own writing, stored as Markdown.' },
  { value: 'transcript', label: 'Transcript', hint: 'YouTube or podcast text with timestamps.' },
  { value: 'web_article', label: 'Web article', hint: 'Article text copied from a browser.' },
  { value: 'markdown', label: 'Markdown', hint: 'Headings become section locators.' },
  { value: 'text', label: 'Plain text', hint: 'No structure assumed.' },
  { value: 'csv', label: 'CSV', hint: 'Rows become row-group locators.' },
  { value: 'json', label: 'JSON', hint: 'Records become JSON-pointer locators.' },
]

export function InboxPage() {
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const mode = params.get('mode') === 'paste' ? 'paste' : 'files'
  const inbox = useAsync(() => api.inbox(), [])
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<ImportResponse | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const [pasteText, setPasteText] = useState('')
  const [pasteKind, setPasteKind] = useState('')
  const [pasteTitle, setPasteTitle] = useState('')
  const [pasteAuthor, setPasteAuthor] = useState('')
  const [pasteUrl, setPasteUrl] = useState('')
  const [pasteTags, setPasteTags] = useState('')
  const [pasting, setPasting] = useState(false)

  const upload = useCallback(
    async (files: File[], force = false) => {
      if (files.length === 0) return
      setUploading(true)
      try {
        const response = await api.importFiles(files, { force })
        setResult(response)
        inbox.reload()
        if (response.created > 0) toast.success(`Imported ${response.created} file(s).`)
        if (response.duplicates > 0) toast.info(`${response.duplicates} duplicate(s) skipped.`)
        if (response.errors + response.rejected > 0) {
          toast.error(`${response.errors + response.rejected} file(s) could not be imported.`)
        }
      } catch (error) {
        toast.error((error as Error).message)
      } finally {
        setUploading(false)
      }
    },
    [inbox, toast],
  )

  const submitPaste = async () => {
    if (!pasteText.trim()) {
      toast.error('Paste something first.')
      return
    }
    setPasting(true)
    try {
      const response = await api.importText({
        text: pasteText,
        kind: pasteKind || undefined,
        title: pasteTitle || undefined,
        author: pasteAuthor || undefined,
        source_url: pasteUrl || undefined,
        tags: parseTagInput(pasteTags),
      })
      setResult(response)
      inbox.reload()
      const item = response.results[0]
      if (item?.status === 'created') {
        toast.success('Imported. Review the detected metadata next.')
        setPasteText('')
        setPasteTitle('')
        setPasteTags('')
      } else if (item?.status === 'duplicate') {
        toast.info(item.message)
      }
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setPasting(false)
    }
  }

  if (inbox.loading && !inbox.data) return <Loading label="Loading inbox" rows={4} />
  if (inbox.error) return <ErrorState message={inbox.error} onRetry={inbox.reload} />
  if (!inbox.data) return null

  const { pending, failed, batches, ocr, limits } = inbox.data

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <h1>Inbox</h1>
          <p className="page__subtitle">
            Drop files or paste text. FORGE extracts and normalises the content, detects metadata and entities,
            and holds the item here until you review it. Duplicates are caught by content hash before anything is
            stored twice.
          </p>
        </div>
        <div className="page__actions">
          <div className="segmented" role="group" aria-label="Import mode">
            <button
              type="button"
              aria-pressed={mode === 'files'}
              onClick={() => {
                params.delete('mode')
                setParams(params, { replace: true })
              }}
            >
              Files
            </button>
            <button type="button" aria-pressed={mode === 'paste'} onClick={() => setParams({ mode: 'paste' })}>
              Paste text
            </button>
          </div>
        </div>
      </header>

      {mode === 'files' ? (
        <section
          className={dragging ? 'dropzone dropzone--active' : 'dropzone'}
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            void upload(Array.from(event.dataTransfer.files))
          }}
          aria-label="File drop area"
        >
          <div className="dropzone__title">{uploading ? 'Importing…' : 'Drop files here'}</div>
          <p className="small">
            PDF · TXT · Markdown · CSV · JSON · VTT/SRT · PNG/JPG/WebP — up to {limits.max_upload_mb} MB per file,{' '}
            {limits.max_batch_files} files per batch.
          </p>
          <div className="btn-group" style={{ justifyContent: 'center' }}>
            <button type="button" className="btn btn--primary" onClick={() => fileInput.current?.click()} disabled={uploading}>
              Choose files
            </button>
            <input
              ref={fileInput}
              type="file"
              multiple
              hidden
              aria-label="Choose files to import"
              onChange={(event) => {
                void upload(Array.from(event.target.files ?? []))
                event.target.value = ''
              }}
            />
          </div>
          {!ocr.available ? (
            <p className="xs faint" style={{ marginTop: 12, marginBottom: 0 }}>
              Screenshots import with their metadata. OCR is optional and currently unavailable: {ocr.detail}
            </p>
          ) : (
            <p className="xs faint" style={{ marginTop: 12, marginBottom: 0 }}>
              OCR is available{ocr.enabled ? ' and enabled for images' : ' — enable it in Settings to index image text'}.
            </p>
          )}
        </section>
      ) : (
        <Section title="Paste content">
          <div className="field-grid">
            <Field label="Type" htmlFor="paste-kind" hint={PASTE_KINDS.find((k) => k.value === pasteKind)?.hint}>
              <select
                id="paste-kind"
                className="select"
                value={pasteKind}
                onChange={(event) => setPasteKind(event.target.value)}
              >
                {PASTE_KINDS.map((kind) => (
                  <option key={kind.value} value={kind.value}>
                    {kind.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Title (optional)" htmlFor="paste-title">
              <input
                id="paste-title"
                className="input"
                value={pasteTitle}
                onChange={(event) => setPasteTitle(event.target.value)}
                placeholder="Detected from the first line when empty"
              />
            </Field>
            <Field label="Author (optional)" htmlFor="paste-author">
              <input
                id="paste-author"
                className="input"
                value={pasteAuthor}
                onChange={(event) => setPasteAuthor(event.target.value)}
              />
            </Field>
            <Field label="Source URL (optional)" htmlFor="paste-url">
              <input
                id="paste-url"
                className="input"
                value={pasteUrl}
                onChange={(event) => setPasteUrl(event.target.value)}
                placeholder="https://…"
              />
            </Field>
          </div>
          <Field label="Tags (optional)" htmlFor="paste-tags" hint="Comma separated.">
            <input
              id="paste-tags"
              className="input"
              value={pasteTags}
              onChange={(event) => setPasteTags(event.target.value)}
              placeholder="transcript, process"
            />
          </Field>
          <Field label="Content" htmlFor="paste-text" hint={`${formatNumber(pasteText.length)} characters`}>
            <textarea
              id="paste-text"
              className="textarea"
              style={{ minHeight: 220 }}
              value={pasteText}
              onChange={(event) => setPasteText(event.target.value)}
              placeholder={'0:00 Host: Welcome back…\n\nor an article, a note, a CSV block…'}
            />
          </Field>
          <div className="btn-group">
            <button type="button" className="btn btn--primary" onClick={() => void submitPaste()} disabled={pasting}>
              {pasting ? 'Importing…' : 'Import text'}
            </button>
            <button type="button" className="btn btn--ghost" onClick={() => setPasteText('')} disabled={!pasteText}>
              Clear
            </button>
          </div>
        </Section>
      )}

      {result ? (
        <Section
          title="Last import"
          action={
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setResult(null)}>
              Dismiss
            </button>
          }
        >
          <div className="row" style={{ marginBottom: 12 }}>
            <Badge tone={result.created ? 'success' : 'neutral'}>{result.created} imported</Badge>
            <Badge tone={result.duplicates ? 'warning' : 'neutral'}>{result.duplicates} duplicates</Badge>
            <Badge tone={result.errors ? 'danger' : 'neutral'}>{result.errors} failed</Badge>
            <Badge tone={result.rejected ? 'danger' : 'neutral'}>{result.rejected} rejected</Badge>
          </div>
          <ul className="list">
            {result.results.map((item, index) => (
              <li key={`${item.filename}-${index}`} className="list__item">
                <div className="list__main">
                  <span className="list__title">{item.title ?? item.filename ?? 'Pasted content'}</span>
                  <span className="list__meta">
                    <Badge
                      tone={
                        item.status === 'created'
                          ? 'success'
                          : item.status === 'duplicate'
                            ? 'warning'
                            : 'danger'
                      }
                    >
                      {item.status}
                    </Badge>
                    <span>{item.message}</span>
                  </span>
                  {item.warnings.length > 0 ? (
                    <ul className="list__meta" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
                      {item.warnings.map((warning) => (
                        <li key={warning}>⚠ {warning}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
                {item.source_id ? (
                  <Link className="btn btn--sm" to={`/inbox/${item.source_id}/review`}>
                    Review
                  </Link>
                ) : null}
                {item.status === 'duplicate' && item.duplicate_of_id ? (
                  <Link className="btn btn--sm" to={`/library/${item.duplicate_of_id}`}>
                    Open original
                  </Link>
                ) : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section title={`Waiting for review (${pending.length})`}>
        {pending.length === 0 ? (
          <EmptyState
            icon="✓"
            title="Nothing waiting"
            body="Imported material appears here until you confirm its metadata and entities."
          />
        ) : (
          <ul className="list">
            {pending.map((source) => (
              <li key={source.id} className="list__item">
                <div className="list__main">
                  <Link className="list__title" to={`/inbox/${source.id}/review`}>
                    {source.title}
                  </Link>
                  <span className="list__meta">
                    <Badge>{SOURCE_KIND_LABELS[source.kind as SourceKind] ?? source.kind}</Badge>
                    <span>{formatNumber(source.word_count)} words</span>
                    <span>{formatBytes(source.byte_size)}</span>
                    <span>{relativeTime(source.imported_at)}</span>
                  </span>
                </div>
                <Link className="btn btn--sm btn--primary" to={`/inbox/${source.id}/review`}>
                  Review
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {failed.length > 0 ? (
        <Section title={`Failed imports (${failed.length})`} description="The original file was kept so you can retry or export it.">
          <ul className="list">
            {failed.map((source) => (
              <li key={source.id} className="list__item">
                <div className="list__main">
                  <span className="list__title">{source.original_filename ?? source.title}</span>
                  <span className="list__meta">
                    <Badge tone="danger">error</Badge>
                    <span>{source.error_message}</span>
                  </span>
                </div>
                <div className="btn-group">
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={async () => {
                      try {
                        await api.reprocess(source.id)
                        toast.success('Reprocessed.')
                        inbox.reload()
                      } catch (error) {
                        toast.error((error as Error).message)
                      }
                    }}
                  >
                    Retry
                  </button>
                  <a className="btn btn--sm" href={api.fileUrl(source.id, true)}>
                    Download original
                  </a>
                  <button
                    type="button"
                    className="btn btn--sm btn--danger"
                    onClick={async () => {
                      if (!window.confirm('Delete this failed import and its stored file?')) return
                      await api.deleteSource(source.id)
                      inbox.reload()
                    }}
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {batches.length > 0 ? (
        <Section title="Recent batches">
          <ul className="list">
            {batches.map((batch) => (
              <li key={batch.id} className="list__item">
                <div className="list__main">
                  <span className="list__title">{batch.label || 'Untitled batch'}</span>
                  <span className="list__meta">
                    <span>{titleCase(`${batch.source_count} sources`)}</span>
                    <span>{relativeTime(batch.created_at)}</span>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </div>
  )
}
