import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Modal } from '../components/Modal'
import { ObjectPicker } from '../components/ObjectPicker'
import type { PickedObject } from '../components/ObjectPicker'
import { TagEditor } from '../components/TagEditor'
import { useToast } from '../components/Toasts'
import { Badge, DemoBadge, EmptyState, ErrorState, Field, GeneratedBadge, Loading, Section } from '../components/ui'
import { api } from '../lib/api'
import {
  formatBytes,
  formatDate,
  formatDateTime,
  formatNumber,
  KNOWLEDGE_KIND_LABELS,
  SOURCE_KIND_LABELS,
  statusTone,
  titleCase,
} from '../lib/format'
import { useAsync, useSelectionInside } from '../lib/hooks'
import type { KnowledgeKind, OperationOutput, SourceKind } from '../lib/types'

const PROMOTE_KINDS: KnowledgeKind[] = ['insight', 'rule', 'hypothesis', 'decision', 'quote', 'note']

export function SourcePage() {
  const { sourceId = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const detail = useAsync(() => api.sourceDetail(sourceId), [sourceId])
  const readerRef = useRef<HTMLDivElement>(null)
  const [readerNode, setReaderNode] = useState<HTMLElement | null>(null)
  const selection = useSelectionInside(readerNode)

  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Record<string, string>>({})
  const [excerptNote, setExcerptNote] = useState('')
  const [promoting, setPromoting] = useState<{ excerptId: string; text: string } | null>(null)
  const [promoteKind, setPromoteKind] = useState<KnowledgeKind>('insight')
  const [promoteTitle, setPromoteTitle] = useState('')
  const [promoteBody, setPromoteBody] = useState('')
  const [linkPickerOpen, setLinkPickerOpen] = useState(false)
  const [operation, setOperation] = useState<OperationOutput | null>(null)
  const [running, setRunning] = useState<string | null>(null)

  useEffect(() => {
    setReaderNode(readerRef.current)
  }, [detail.data])

  useEffect(() => {
    if (!detail.data) return
    const { source } = detail.data
    setForm({
      title: source.title,
      author: source.author ?? '',
      publisher: source.publisher ?? '',
      source_url: source.source_url ?? '',
      published_on: source.published_on ?? '',
      language: source.language ?? '',
      summary: source.summary ?? '',
    })
  }, [detail.data])

  const documents = detail.data?.documents ?? []
  const excerpts = detail.data?.excerpts ?? []
  const totalChars = useMemo(() => detail.data?.source.char_count ?? 0, [detail.data])

  if (detail.loading && !detail.data) return <Loading label="Loading source" rows={6} />
  if (detail.error) return <ErrorState message={detail.error} onRetry={detail.reload} />
  if (!detail.data) return null

  const { source, entities, links, warnings, detected_metadata } = detail.data

  const saveMetadata = async () => {
    try {
      await api.updateSource(sourceId, {
        title: form.title,
        author: form.author || null,
        publisher: form.publisher || null,
        source_url: form.source_url || null,
        published_on: form.published_on || null,
        language: form.language || null,
        summary: form.summary || null,
      })
      toast.success('Metadata saved.')
      setEditing(false)
      detail.reload()
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const createExcerpt = async () => {
    if (!selection?.text) return
    try {
      await api.createExcerpt(sourceId, {
        text: selection.text,
        char_start: selection.offset ?? undefined,
        char_end: selection.offset !== null && selection.offset !== undefined ? selection.offset + selection.text.length : undefined,
        note: excerptNote || undefined,
      })
      toast.success('Excerpt saved with its locator.')
      setExcerptNote('')
      window.getSelection()?.removeAllRanges()
      detail.reload()
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const runOperation = async (op: string) => {
    setRunning(op)
    try {
      const output = await api.runOperation({ operation: op, source_id: sourceId })
      setOperation(output)
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setRunning(null)
    }
  }

  const addLink = async (picked: PickedObject) => {
    try {
      await api.createLink({
        from_type: 'source',
        from_id: sourceId,
        to_type: picked.target_type,
        to_id: picked.target_id,
        relation: picked.target_type === 'dossier' ? 'part_of' : 'related_to',
      })
      toast.success(`Linked to ${picked.label}.`)
      detail.reload()
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const submitPromotion = async () => {
    if (!promoting) return
    try {
      const created = await api.promoteExcerpt(promoting.excerptId, {
        kind: promoteKind,
        title: promoteTitle || promoting.text.slice(0, 90),
        body: promoteBody,
      })
      toast.success(`${KNOWLEDGE_KIND_LABELS[promoteKind]} created from the excerpt.`)
      setPromoting(null)
      setPromoteTitle('')
      setPromoteBody('')
      navigate(`/knowledge?focus=${created.id}`)
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <div className="row" style={{ gap: 8 }}>
            <Badge>{SOURCE_KIND_LABELS[source.kind as SourceKind] ?? source.kind}</Badge>
            <Badge tone={statusTone(source.status)}>{titleCase(source.status)}</Badge>
            {source.is_demo ? <DemoBadge /> : null}
          </div>
          <h1>{source.title}</h1>
          <p className="page__subtitle">
            {source.author ? `${source.author} · ` : ''}
            {source.published_on ? `${formatDate(source.published_on)} · ` : ''}
            {formatNumber(source.word_count)} words · {documents.length} units · imported{' '}
            {formatDateTime(source.imported_at)}
          </p>
        </div>
        <div className="page__actions">
          {source.status === 'needs_review' ? (
            <Link className="btn btn--primary" to={`/inbox/${source.id}/review`}>
              Review
            </Link>
          ) : null}
          {source.has_original ? (
            <a className="btn" href={api.fileUrl(source.id)} target="_blank" rel="noreferrer">
              Open original
            </a>
          ) : null}
          <a className="btn" href={api.sourceMarkdownUrl(source.id)}>
            Export Markdown
          </a>
          <button type="button" className="btn" onClick={() => setLinkPickerOpen(true)}>
            Link to…
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={async () => {
              if (!window.confirm('Delete this source, its excerpts and its stored original?')) return
              await api.deleteSource(sourceId)
              toast.success('Source deleted.')
              navigate('/library')
            }}
          >
            Delete
          </button>
        </div>
      </header>

      {warnings.length > 0 ? (
        <div className="notice notice--warning">
          <strong>Extraction warnings</strong>
          <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {source.error_message ? (
        <ErrorState message={source.error_message} onRetry={() => api.reprocess(sourceId).then(() => detail.reload())} />
      ) : null}

      <div className="split split--wide">
        <div className="stack">
          <Section
            title="Extracted text"
            description="Select any passage to save it as an excerpt. The locator (page, timestamp, section, row) is taken from the unit the selection starts in."
            action={<span className="xs faint">{formatNumber(totalChars)} characters</span>}
          >
            {documents.length === 0 ? (
              <EmptyState icon="≡" title="No text layer" body="This source has no extracted text. Add a note instead, or enable OCR for images." />
            ) : (
              <>
                <div className="reader" ref={readerRef}>
                  {documents.map((unit) => (
                    <div key={unit.id} className="reader__unit">
                      <div className="reader__locator">
                        <span>{unit.locator_label || `${unit.kind} ${unit.ordinal + 1}`}</span>
                        {unit.title ? <span className="faint">· {unit.title}</span> : null}
                      </div>
                      <pre className="reader__text" data-char-start={unit.char_start}>
                        {unit.text}
                      </pre>
                    </div>
                  ))}
                </div>
                {selection?.text ? (
                  <div className="card" style={{ marginTop: 12 }}>
                    <div className="stack stack--tight">
                      <strong className="small">Selected passage</strong>
                      <blockquote className="quote small">{selection.text}</blockquote>
                      <Field label="Note (optional)" htmlFor="excerpt-note">
                        <input
                          id="excerpt-note"
                          className="input"
                          value={excerptNote}
                          onChange={(event) => setExcerptNote(event.target.value)}
                          placeholder="Why this passage matters"
                        />
                      </Field>
                      <div className="btn-group">
                        <button type="button" className="btn btn--primary btn--sm" onClick={() => void createExcerpt()}>
                          Save excerpt
                        </button>
                        <span className="xs faint">
                          {selection.offset !== null
                            ? `offset ${formatNumber(selection.offset)}`
                            : 'offset will be resolved by text match'}
                        </span>
                      </div>
                    </div>
                  </div>
                ) : null}
              </>
            )}
          </Section>

          <Section title={`Excerpts (${excerpts.length})`}>
            {excerpts.length === 0 ? (
              <EmptyState icon="❝" title="No excerpts yet" body="Select text above to quote it. Excerpts are what insights, rules and dossier claims are built from." />
            ) : (
              <ul className="list">
                {excerpts.map((excerpt) => (
                  <li key={excerpt.id} className="list__item" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                    <blockquote className="quote quote--evidence">{excerpt.text}</blockquote>
                    <div className="row row--between" style={{ marginTop: 8 }}>
                      <div className="provenance">
                        <span className="provenance__locator">
                          {'locator_label' in excerpt.provenance ? String(excerpt.provenance.locator_label) : ''}
                        </span>
                        {excerpt.note ? <span>· {excerpt.note}</span> : null}
                        {excerpt.used_by.length > 0 ? (
                          <span>
                            · used in{' '}
                            {excerpt.used_by.map((usage, index) => (
                              <span key={`${usage.target_type}-${usage.target_id}`}>
                                {index > 0 ? ', ' : ''}
                                <Link
                                  to={
                                    usage.target_type === 'dossier'
                                      ? `/dossiers/${usage.target_id}`
                                      : `/knowledge?focus=${usage.target_id}`
                                  }
                                >
                                  {usage.label}
                                </Link>
                              </span>
                            ))}
                          </span>
                        ) : null}
                      </div>
                      <div className="btn-group">
                        <button
                          type="button"
                          className="btn btn--sm"
                          onClick={() => {
                            setPromoting({ excerptId: excerpt.id, text: excerpt.text })
                            setPromoteTitle(excerpt.text.slice(0, 90))
                            setPromoteBody('')
                          }}
                        >
                          Promote
                        </button>
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          onClick={async () => {
                            if (!window.confirm('Delete this excerpt?')) return
                            await api.deleteExcerpt(excerpt.id)
                            detail.reload()
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section
            title="Assisted analysis"
            description="Runs locally. Without a local model these operations fall back to deterministic extraction and say so."
          >
            <div className="btn-group">
              {[
                ['summarize', 'Summarise'],
                ['extract_entities', 'Extract entities'],
                ['suggest_topics', 'Suggest topics'],
                ['extract_claims', 'Extract claims'],
              ].map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className="btn btn--sm"
                  onClick={() => void runOperation(key)}
                  disabled={running !== null}
                >
                  {running === key ? 'Running…' : label}
                </button>
              ))}
            </div>

            {operation ? (
              <div className={operation.generated ? 'notice notice--generated' : 'notice'} style={{ marginTop: 12 }}>
                <div className="row row--between">
                  <strong>
                    {titleCase(operation.operation)}{' '}
                    {operation.generated ? <GeneratedBadge by={operation.model} /> : <Badge>deterministic</Badge>}
                  </strong>
                  <button type="button" className="btn btn--ghost btn--sm" onClick={() => setOperation(null)}>
                    Dismiss
                  </button>
                </div>
                <p className="small" style={{ marginTop: 8 }}>
                  {operation.notice}
                </p>
                {operation.fallback_reason ? (
                  <p className="xs faint">Local model unavailable: {operation.fallback_reason}</p>
                ) : null}
                {operation.text ? <blockquote className="quote small">{operation.text}</blockquote> : null}
                {operation.items.length > 0 ? (
                  <ul className="small" style={{ paddingLeft: 18, marginBottom: 0 }}>
                    {operation.items.slice(0, 12).map((item, index) => (
                      <li key={index}>
                        {String(item.name ?? item.text ?? item.quote ?? JSON.stringify(item))}
                        {item.kind ? <span className="faint"> · {String(item.kind)}</span> : null}
                        {item.confidence ? <span className="faint"> · {String(item.confidence)}</span> : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {operation.operation === 'summarize' && operation.text ? (
                  <div className="btn-group" style={{ marginTop: 10 }}>
                    <button
                      type="button"
                      className="btn btn--sm"
                      onClick={async () => {
                        await api.updateSource(sourceId, { summary: operation.text })
                        toast.success('Summary saved to the source (editable at any time).')
                        detail.reload()
                      }}
                    >
                      Save as source summary
                    </button>
                  </div>
                ) : null}
                {operation.operation === 'suggest_topics' && operation.items.length > 0 ? (
                  <div className="btn-group" style={{ marginTop: 10 }}>
                    <button
                      type="button"
                      className="btn btn--sm"
                      onClick={async () => {
                        const names = operation.items
                          .map((item) => String(item.name ?? ''))
                          .filter(Boolean)
                        await api.setSourceTags(sourceId, [
                          ...source.tags.map((tag) => tag.name),
                          ...names,
                        ])
                        toast.success('Tags added.')
                        detail.reload()
                      }}
                    >
                      Add all as tags
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </Section>
        </div>

        <div className="stack">
          <Section
            title="Metadata"
            action={
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing((value) => !value)}>
                {editing ? 'Cancel' : 'Edit'}
              </button>
            }
          >
            {editing ? (
              <div className="stack stack--tight">
                {[
                  ['title', 'Title'],
                  ['author', 'Author'],
                  ['publisher', 'Publisher'],
                  ['source_url', 'Source URL'],
                  ['language', 'Language'],
                ].map(([key, label]) => (
                  <Field key={key} label={label} htmlFor={`meta-${key}`}>
                    <input
                      id={`meta-${key}`}
                      className="input"
                      value={form[key] ?? ''}
                      onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}
                    />
                  </Field>
                ))}
                <Field label="Published on" htmlFor="meta-published">
                  <input
                    id="meta-published"
                    className="input"
                    type="date"
                    value={form.published_on ?? ''}
                    onChange={(event) => setForm((current) => ({ ...current, published_on: event.target.value }))}
                  />
                </Field>
                <Field label="Summary" htmlFor="meta-summary">
                  <textarea
                    id="meta-summary"
                    className="textarea"
                    value={form.summary ?? ''}
                    onChange={(event) => setForm((current) => ({ ...current, summary: event.target.value }))}
                  />
                </Field>
                <button type="button" className="btn btn--primary btn--sm" onClick={() => void saveMetadata()}>
                  Save metadata
                </button>
              </div>
            ) : (
              <ul className="list">
                <li className="list__item">
                  <div className="list__main">
                    <span className="list__title">{source.author ?? 'No author recorded'}</span>
                    <span className="list__meta">{source.publisher ?? 'No publisher'}</span>
                  </div>
                </li>
                <li className="list__item">
                  <div className="list__main">
                    <span className="list__title">{formatDate(source.published_on)}</span>
                    <span className="list__meta">Publication date</span>
                  </div>
                </li>
                <li className="list__item">
                  <div className="list__main">
                    <span className="list__title mono xs">{source.extraction_method}</span>
                    <span className="list__meta">
                      {formatBytes(source.byte_size)} · {source.mime_type ?? 'unknown type'} ·{' '}
                      {source.language ?? 'language unknown'}
                    </span>
                  </div>
                </li>
                <li className="list__item">
                  <div className="list__main">
                    <span className="list__title xs mono">{source.content_hash.slice(0, 32)}…</span>
                    <span className="list__meta">SHA-256 of the original bytes</span>
                  </div>
                </li>
                {source.source_url ? (
                  <li className="list__item">
                    <div className="list__main">
                      <a className="list__title" href={source.source_url} target="_blank" rel="noreferrer noopener">
                        {source.source_url}
                      </a>
                      <span className="list__meta">Source URL</span>
                    </div>
                  </li>
                ) : null}
              </ul>
            )}
            {source.summary && !editing ? (
              <>
                <div className="field__label" style={{ marginTop: 12 }}>
                  Summary
                </div>
                <p className="small">{source.summary}</p>
              </>
            ) : null}
          </Section>

          <Section title="Tags">
            <TagEditor
              tags={source.tags}
              onSave={async (names) => {
                await api.setSourceTags(sourceId, names)
                toast.success('Tags updated.')
                detail.reload()
              }}
            />
          </Section>

          <Section title={`Entities (${entities.length})`}>
            {entities.length === 0 ? (
              <p className="small muted mt-0">No confirmed entities. Review the source to attach the detected ones.</p>
            ) : (
              <ul className="list">
                {entities.map((entity) => (
                  <li key={entity.id} className="list__item">
                    <div className="list__main">
                      <Link className="list__title" to={`/library?entity_id=${entity.id}`}>
                        {entity.name}
                      </Link>
                      <span className="list__meta">
                        <Badge>{entity.kind}</Badge>
                        <span>{entity.count} mention(s)</span>
                        <span className="mono xs">{entity.detector}</span>
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title={`Links (${links.length})`}>
            {links.length === 0 ? (
              <p className="small muted mt-0">Not linked to anything yet.</p>
            ) : (
              <ul className="list">
                {links.map((link) => (
                  <li key={link.link_id} className="list__item">
                    <div className="list__main">
                      <Link
                        className="list__title"
                        to={
                          link.target_type === 'dossier'
                            ? `/dossiers/${link.target_id}`
                            : link.target_type === 'source'
                              ? `/library/${link.target_id}`
                              : `/knowledge?focus=${link.target_id}`
                        }
                      >
                        {link.label}
                      </Link>
                      <span className="list__meta">
                        <Badge>{link.relation}</Badge>
                        <span>{link.target_type}</span>
                        <span className="faint">{link.direction}</span>
                      </span>
                    </div>
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={async () => {
                        await api.deleteLink(link.link_id)
                        detail.reload()
                      }}
                      aria-label={`Remove link to ${link.label}`}
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Detected on import" description="What the deterministic extractor found. Kept for auditing.">
            <pre className="xs faint" style={{ maxHeight: 220, overflow: 'auto' }}>
              {JSON.stringify(detected_metadata, null, 2)}
            </pre>
          </Section>
        </div>
      </div>

      <Modal
        open={promoting !== null}
        title="Promote excerpt"
        onClose={() => setPromoting(null)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setPromoting(null)}>
              Cancel
            </button>
            <button type="button" className="btn btn--primary" onClick={() => void submitPromotion()}>
              Create {KNOWLEDGE_KIND_LABELS[promoteKind]}
            </button>
          </>
        }
      >
        {promoting ? (
          <div className="stack stack--tight">
            <blockquote className="quote small">{promoting.text}</blockquote>
            <p className="xs faint">
              The excerpt stays attached as evidence, and the new object is linked back to this source with
              <code> derived_from</code>.
            </p>
            <Field label="Type" htmlFor="promote-kind">
              <select
                id="promote-kind"
                className="select"
                value={promoteKind}
                onChange={(event) => setPromoteKind(event.target.value as KnowledgeKind)}
              >
                {PROMOTE_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {KNOWLEDGE_KIND_LABELS[kind]}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Title" htmlFor="promote-title">
              <input
                id="promote-title"
                className="input"
                value={promoteTitle}
                onChange={(event) => setPromoteTitle(event.target.value)}
              />
            </Field>
            <Field label="Body" htmlFor="promote-body" hint="Left empty, the excerpt text is used.">
              <textarea
                id="promote-body"
                className="textarea"
                value={promoteBody}
                onChange={(event) => setPromoteBody(event.target.value)}
              />
            </Field>
          </div>
        ) : null}
      </Modal>

      <ObjectPicker
        open={linkPickerOpen}
        onClose={() => setLinkPickerOpen(false)}
        onPick={(picked) => void addLink(picked)}
        title="Link this source to…"
        types={['dossier', 'knowledge', 'entity', 'source']}
        excludeIds={[sourceId]}
      />
    </div>
  )
}
