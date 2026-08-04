import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Modal } from '../components/Modal'
import { ObjectPicker } from '../components/ObjectPicker'
import { TagEditor } from '../components/TagEditor'
import { useToast } from '../components/Toasts'
import { Badge, DemoBadge, EmptyState, ErrorState, Field, GeneratedBadge, Loading, Section } from '../components/ui'
import { api } from '../lib/api'
import {
  confidenceLabel,
  formatDate,
  KNOWLEDGE_KIND_ICONS,
  KNOWLEDGE_KIND_LABELS,
  relativeTime,
  stanceTone,
  statusTone,
  titleCase,
} from '../lib/format'
import { useAsync } from '../lib/hooks'
import { Markdown } from '../lib/markdown'
import type { KnowledgeKind } from '../lib/types'

const KINDS: KnowledgeKind[] = ['insight', 'rule', 'hypothesis', 'decision', 'quote', 'note']

export function KnowledgePage() {
  const [params, setParams] = useSearchParams()
  const toast = useToast()
  const focusId = params.get('focus')
  const [kinds, setKinds] = useState<string[]>(params.getAll('kind'))
  const [query, setQuery] = useState('')
  const [hasEvidence, setHasEvidence] = useState<string>(params.get('has_evidence') ?? '')
  const [creating, setCreating] = useState(params.get('new') === '1')
  const [selectedId, setSelectedId] = useState<string | null>(focusId)
  const [evidencePickerOpen, setEvidencePickerOpen] = useState(false)

  const [form, setForm] = useState({ kind: 'insight' as KnowledgeKind, title: '', body: '', confidence: '', tags: '' })

  const list = useAsync(
    () =>
      api.knowledge({
        kind: kinds,
        q: query || undefined,
        has_evidence: hasEvidence === '' ? undefined : hasEvidence === 'true',
        limit: 200,
      }),
    [kinds.join(','), query, hasEvidence],
  )
  const detail = useAsync(async () => (selectedId ? api.knowledgeDetail(selectedId) : null), [selectedId, list.data])

  useEffect(() => {
    if (params.get('new') === '1') {
      setCreating(true)
      params.delete('new')
      setParams(params, { replace: true })
    }
  }, [params, setParams])

  useEffect(() => {
    if (focusId) setSelectedId(focusId)
  }, [focusId])

  useEffect(() => {
    if (!selectedId && list.data?.items.length) setSelectedId(list.data.items[0].id)
  }, [list.data, selectedId])

  const create = async () => {
    if (!form.title.trim()) {
      toast.error('A title is required.')
      return
    }
    try {
      const created = await api.createKnowledge({
        kind: form.kind,
        title: form.title.trim(),
        body: form.body,
        confidence: form.confidence ? Number(form.confidence) : null,
        tags: form.tags
          .split(',')
          .map((tag) => tag.trim())
          .filter(Boolean),
      })
      toast.success(`${KNOWLEDGE_KIND_LABELS[form.kind]} created.`)
      setCreating(false)
      setForm({ kind: form.kind, title: '', body: '', confidence: '', tags: '' })
      setSelectedId(created.id)
      list.reload()
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const items = list.data?.items ?? []
  const facets = list.data?.facets?.kind ?? {}
  const selected = detail.data?.knowledge ?? null

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <h1>Knowledge</h1>
          <p className="page__subtitle">
            Insights, trading rules, hypotheses, decisions, quotes and research notes — each one backed by the
            excerpts it came from, and each excerpt still pointing at its page, timestamp, section or row.
          </p>
        </div>
        <div className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => setCreating(true)}>
            New knowledge object
          </button>
        </div>
      </header>

      <div className="row">
        <input
          className="input"
          style={{ maxWidth: 320 }}
          placeholder="Filter by title or body…"
          aria-label="Filter knowledge"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="chip-row">
          {KINDS.map((kind) => (
            <button
              key={kind}
              type="button"
              className="chip"
              aria-pressed={kinds.includes(kind)}
              onClick={() =>
                setKinds((current) =>
                  current.includes(kind) ? current.filter((item) => item !== kind) : [...current, kind],
                )
              }
            >
              {KNOWLEDGE_KIND_ICONS[kind]} {KNOWLEDGE_KIND_LABELS[kind]}
              {facets[kind] ? <span className="faint"> {facets[kind]}</span> : null}
            </button>
          ))}
        </div>
        <select
          className="select"
          style={{ width: 'auto' }}
          aria-label="Evidence filter"
          value={hasEvidence}
          onChange={(event) => setHasEvidence(event.target.value)}
        >
          <option value="">Any evidence state</option>
          <option value="true">With evidence</option>
          <option value="false">Without evidence</option>
        </select>
      </div>

      {list.loading && !list.data ? <Loading label="Loading knowledge" rows={5} /> : null}
      {list.error ? <ErrorState message={list.error} onRetry={list.reload} /> : null}

      {!list.loading && items.length === 0 ? (
        <EmptyState
          icon="✦"
          title="No knowledge objects yet"
          body="Select a passage in any source and promote it, or create one here and attach evidence afterwards."
          action={
            <Link className="btn btn--primary" to="/library">
              Open the library
            </Link>
          }
        />
      ) : null}

      {items.length > 0 ? (
        <div className="split split--wide">
          <div className="card card--flush">
            <ul className="list" style={{ padding: 'var(--space-2) var(--space-4)' }}>
              {items.map((item) => (
                <li key={item.id} className="list__item">
                  <div className="list__main">
                    <button
                      type="button"
                      className="list__title"
                      style={{ background: 'none', border: 'none', padding: 0, textAlign: 'left', color: 'inherit', cursor: 'pointer', font: 'inherit' }}
                      onClick={() => setSelectedId(item.id)}
                      aria-current={selectedId === item.id}
                    >
                      {KNOWLEDGE_KIND_ICONS[item.kind]} {item.title}
                    </button>
                    <span className="list__meta">
                      <Badge>{KNOWLEDGE_KIND_LABELS[item.kind]}</Badge>
                      <Badge tone={statusTone(item.status)}>{titleCase(item.status)}</Badge>
                      {item.origin === 'generated' ? <GeneratedBadge by={item.generated_by} /> : null}
                      {item.is_demo ? <DemoBadge /> : null}
                      <span>{item.evidence.length} evidence</span>
                      <span>{relativeTime(item.updated_at)}</span>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div className="stack">
            {detail.loading && !selected ? <Loading label="Loading" rows={3} /> : null}
            {selected ? (
              <>
                <Section
                  title={selected.title}
                  action={
                    <div className="btn-group">
                      <a className="btn btn--ghost btn--sm" href={api.knowledgeMarkdownUrl(selected.id)}>
                        Export
                      </a>
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={async () => {
                          if (!window.confirm('Delete this knowledge object?')) return
                          await api.deleteKnowledge(selected.id)
                          setSelectedId(null)
                          list.reload()
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  }
                >
                  <div className="row" style={{ gap: 8, marginBottom: 10 }}>
                    <Badge>{KNOWLEDGE_KIND_LABELS[selected.kind]}</Badge>
                    <select
                      className="select"
                      style={{ width: 'auto' }}
                      aria-label="Status"
                      value={selected.status}
                      onChange={async (event) => {
                        await api.updateKnowledge(selected.id, { status: event.target.value })
                        detail.reload()
                        list.reload()
                      }}
                    >
                      {(detail.data?.allowed_statuses ?? []).map((status) => (
                        <option key={status} value={status}>
                          {titleCase(status)}
                        </option>
                      ))}
                    </select>
                    <input
                      className="input"
                      style={{ width: 120 }}
                      type="number"
                      min={0}
                      max={100}
                      aria-label="Confidence"
                      defaultValue={selected.confidence ?? ''}
                      placeholder="confidence"
                      onBlur={async (event) => {
                        const value = event.target.value
                        await api.updateKnowledge(selected.id, { confidence: value === '' ? null : Number(value) })
                        detail.reload()
                      }}
                    />
                    <span className="xs faint">{confidenceLabel(selected.confidence)}</span>
                    {selected.review_due_on ? (
                      <Badge tone="warning">review {formatDate(selected.review_due_on)}</Badge>
                    ) : null}
                  </div>

                  {selected.origin === 'generated' ? (
                    <div className="notice notice--generated" style={{ marginBottom: 12 }}>
                      <GeneratedBadge by={selected.generated_by} /> This text was drafted by a local model and kept
                      editable. It is not a verified fact.
                    </div>
                  ) : null}

                  <Markdown text={selected.body} />

                  <div className="stack stack--tight" style={{ marginTop: 12 }}>
                    <span className="field__label">Edit body</span>
                    <textarea
                      className="textarea"
                      defaultValue={selected.body}
                      aria-label="Knowledge body"
                      onBlur={async (event) => {
                        if (event.target.value === selected.body) return
                        await api.updateKnowledge(selected.id, { body: event.target.value })
                        toast.success('Saved.')
                        detail.reload()
                        list.reload()
                      }}
                    />
                    <span className="field__hint">Saved when the field loses focus. Markdown supported.</span>
                  </div>

                  {selected.outcome ? (
                    <>
                      <div className="field__label" style={{ marginTop: 12 }}>
                        Outcome
                      </div>
                      <Markdown text={selected.outcome} />
                    </>
                  ) : null}
                </Section>

                <Section
                  title={`Evidence (${selected.evidence.length})`}
                  action={
                    <button type="button" className="btn btn--sm" onClick={() => setEvidencePickerOpen(true)}>
                      Attach excerpt
                    </button>
                  }
                >
                  {selected.evidence.length === 0 ? (
                    <EmptyState
                      icon="❝"
                      title="No evidence attached"
                      body="Attach the excerpt this came from so the claim stays traceable."
                    />
                  ) : (
                    <ul className="list">
                      {selected.evidence.map((evidence) => (
                        <li key={evidence.id} className="list__item" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                          <blockquote className="quote quote--evidence">{evidence.text}</blockquote>
                          <div className="row row--between" style={{ marginTop: 6 }}>
                            <div className="provenance">
                              <Badge tone={stanceTone(evidence.stance)}>{evidence.stance}</Badge>
                              {evidence.source_id ? (
                                <Link to={`/library/${evidence.source_id}`}>{evidence.source_title}</Link>
                              ) : (
                                <span>{evidence.source_title}</span>
                              )}
                              {evidence.locator_label ? (
                                <span className="provenance__locator">{evidence.locator_label}</span>
                              ) : null}
                              {evidence.note ? <span>· {evidence.note}</span> : null}
                            </div>
                            <button
                              type="button"
                              className="btn btn--ghost btn--sm"
                              onClick={async () => {
                                await api.removeEvidence(selected.id, evidence.id)
                                detail.reload()
                                list.reload()
                              }}
                            >
                              Detach
                            </button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </Section>

                <Section title="Tags">
                  <TagEditor
                    tags={selected.tags}
                    onSave={async (names) => {
                      await api.setKnowledgeTags(selected.id, names)
                      detail.reload()
                      list.reload()
                    }}
                  />
                </Section>

                {(detail.data?.links.length ?? 0) > 0 ? (
                  <Section title="Relationships">
                    <ul className="list">
                      {detail.data?.links.map((link) => (
                        <li key={link.link_id} className="list__item">
                          <div className="list__main">
                            <Link
                              className="list__title"
                              to={
                                link.target_type === 'source'
                                  ? `/library/${link.target_id}`
                                  : link.target_type === 'dossier'
                                    ? `/dossiers/${link.target_id}`
                                    : `/knowledge?focus=${link.target_id}`
                              }
                            >
                              {link.label}
                            </Link>
                            <span className="list__meta">
                              <Badge>{link.relation}</Badge>
                              <span>{link.target_type}</span>
                            </span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </Section>
                ) : null}
              </>
            ) : null}
          </div>
        </div>
      ) : null}

      <Modal
        open={creating}
        title="New knowledge object"
        onClose={() => setCreating(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn--primary" onClick={() => void create()}>
              Create
            </button>
          </>
        }
      >
        <Field label="Type" htmlFor="knowledge-kind">
          <select
            id="knowledge-kind"
            className="select"
            value={form.kind}
            onChange={(event) => setForm((current) => ({ ...current, kind: event.target.value as KnowledgeKind }))}
          >
            {KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {KNOWLEDGE_KIND_LABELS[kind]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Title" htmlFor="knowledge-title">
          <input
            id="knowledge-title"
            className="input"
            autoFocus
            value={form.title}
            onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
          />
        </Field>
        <Field label="Body" htmlFor="knowledge-body" hint="Markdown supported.">
          <textarea
            id="knowledge-body"
            className="textarea"
            value={form.body}
            onChange={(event) => setForm((current) => ({ ...current, body: event.target.value }))}
          />
        </Field>
        <div className="field-grid">
          <Field label="Confidence (0-100)" htmlFor="knowledge-confidence">
            <input
              id="knowledge-confidence"
              className="input"
              type="number"
              min={0}
              max={100}
              value={form.confidence}
              onChange={(event) => setForm((current) => ({ ...current, confidence: event.target.value }))}
            />
          </Field>
          <Field label="Tags" htmlFor="knowledge-tags">
            <input
              id="knowledge-tags"
              className="input"
              value={form.tags}
              onChange={(event) => setForm((current) => ({ ...current, tags: event.target.value }))}
            />
          </Field>
        </div>
      </Modal>

      <ObjectPicker
        open={evidencePickerOpen}
        onClose={() => setEvidencePickerOpen(false)}
        onPick={async (picked) => {
          if (!selected) return
          try {
            await api.addEvidence(selected.id, { excerpt_id: picked.target_id, stance: 'supports' })
            toast.success('Evidence attached.')
            detail.reload()
            list.reload()
          } catch (error) {
            toast.error((error as Error).message)
          }
        }}
        title="Attach an excerpt as evidence"
        types={['excerpt']}
      />
    </div>
  )
}
