import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Modal } from '../components/Modal'
import { ObjectPicker } from '../components/ObjectPicker'
import type { PickedObject } from '../components/ObjectPicker'
import { TagEditor } from '../components/TagEditor'
import { useToast } from '../components/Toasts'
import { Badge, DemoBadge, EmptyState, ErrorState, Field, GeneratedBadge, Loading, Section } from '../components/ui'
import { Markdown } from '../lib/markdown'
import { api } from '../lib/api'
import { confidenceLabel, formatDate, relativeTime, stanceTone, statusTone, titleCase } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { OperationOutput } from '../lib/types'

const PROSE_FIELDS: Array<{ key: 'overview' | 'thesis' | 'bull_case' | 'bear_case' | 'risks' | 'open_questions'; label: string; hint: string }> = [
  { key: 'overview', label: 'Overview', hint: 'What this dossier is about and why it exists.' },
  { key: 'thesis', label: 'Thesis', hint: 'The one-paragraph version you would defend.' },
  { key: 'bull_case', label: 'Bull case', hint: 'The strongest version of the argument for.' },
  { key: 'bear_case', label: 'Bear case', hint: 'The strongest version of the argument against.' },
  { key: 'risks', label: 'Risks', hint: 'What would damage the thesis, and how you would notice.' },
  { key: 'open_questions', label: 'Open questions', hint: 'What you still cannot answer.' },
]

const SECTION_LABELS: Record<string, string> = {
  sources: 'Linked sources',
  evidence: 'Linked excerpts',
  knowledge: 'Knowledge objects',
  entities: 'Related entities',
  notes: 'Notes',
  watchlist: 'Watchlist',
}

export function DossierPage() {
  const { dossierId = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const state = useAsync(() => api.dossier(dossierId), [dossierId])

  const [editingField, setEditingField] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [pickerSection, setPickerSection] = useState<string | null>(null)
  const [claimText, setClaimText] = useState('')
  const [claimStance, setClaimStance] = useState('neutral')
  const [claimConfidence, setClaimConfidence] = useState('')
  const [evidenceFor, setEvidenceFor] = useState<string | null>(null)
  const [eventOpen, setEventOpen] = useState(false)
  const [eventDate, setEventDate] = useState('')
  const [eventTitle, setEventTitle] = useState('')
  const [eventDescription, setEventDescription] = useState('')
  const [exportPreview, setExportPreview] = useState<string | null>(null)
  const [questions, setQuestions] = useState<OperationOutput | null>(null)

  if (state.loading && !state.data) return <Loading label="Loading dossier" rows={6} />
  if (state.error) return <ErrorState message={state.error} onRetry={state.reload} />
  if (!state.data) return null

  const { dossier, items, claims, timeline, related_entities, links, counts } = state.data
  const bySection = items.reduce<Record<string, typeof items>>((accumulator, item) => {
    ;(accumulator[item.section] ??= []).push(item)
    return accumulator
  }, {})

  const saveField = async (key: string) => {
    try {
      await api.updateDossier(dossierId, { [key]: draft })
      toast.success(`${titleCase(key)} saved.`)
      setEditingField(null)
      state.reload()
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const addItem = async (picked: PickedObject, section: string) => {
    try {
      await api.addDossierItem(dossierId, {
        target_type: picked.target_type,
        target_id: picked.target_id,
        section,
      })
      toast.success(`${picked.label} added.`)
      state.reload()
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const addClaim = async () => {
    if (!claimText.trim()) return
    try {
      await api.addClaim(dossierId, {
        text: claimText.trim(),
        stance: claimStance,
        confidence: claimConfidence ? Number(claimConfidence) : null,
      })
      setClaimText('')
      setClaimConfidence('')
      state.reload()
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const addEvent = async () => {
    if (!eventDate || !eventTitle.trim()) {
      toast.error('An event needs a date and a title.')
      return
    }
    try {
      await api.addEvent(dossierId, {
        occurred_on: eventDate,
        title: eventTitle.trim(),
        description: eventDescription || null,
      })
      setEventOpen(false)
      setEventTitle('')
      setEventDescription('')
      state.reload()
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <div className="row" style={{ gap: 8 }}>
            <Badge>{titleCase(dossier.subject_kind)}</Badge>
            <Badge tone={statusTone(dossier.status)}>{titleCase(dossier.status)}</Badge>
            {dossier.is_demo ? <DemoBadge /> : null}
            <span className="xs faint">updated {relativeTime(dossier.updated_at)}</span>
          </div>
          <h1>{dossier.title}</h1>
          <p className="page__subtitle">
            {counts.sources ?? 0} sources · {claims.length} claims · {timeline.length} timeline events ·{' '}
            {related_entities.length} related entities
          </p>
        </div>
        <div className="page__actions">
          <select
            className="select"
            style={{ width: 'auto' }}
            aria-label="Dossier status"
            value={dossier.status}
            onChange={async (event) => {
              await api.updateDossier(dossierId, { status: event.target.value })
              state.reload()
            }}
          >
            {['active', 'watching', 'archived'].map((status) => (
              <option key={status} value={status}>
                {titleCase(status)}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn"
            onClick={async () => {
              const markdown = await api.dossierMarkdown(dossierId)
              setExportPreview(typeof markdown === 'string' ? markdown : (markdown as { markdown: string }).markdown)
            }}
          >
            Preview export
          </button>
          <a className="btn" href={api.dossierMarkdownUrl(dossierId)}>
            Export Markdown
          </a>
          <a className="btn" href={api.dossierBundleUrl(dossierId)}>
            Export bundle
          </a>
          <button
            type="button"
            className="btn btn--danger"
            onClick={async () => {
              if (!window.confirm('Delete this dossier? Linked sources and knowledge objects are kept.')) return
              await api.deleteDossier(dossierId)
              toast.success('Dossier deleted.')
              navigate('/dossiers')
            }}
          >
            Delete
          </button>
        </div>
      </header>

      <div className="split split--wide">
        <div className="stack">
          {PROSE_FIELDS.map((field) => (
            <Section
              key={field.key}
              title={field.label}
              action={
                editingField === field.key ? (
                  <div className="btn-group">
                    <button type="button" className="btn btn--primary btn--sm" onClick={() => void saveField(field.key)}>
                      Save
                    </button>
                    <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditingField(null)}>
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => {
                      setDraft(dossier[field.key] ?? '')
                      setEditingField(field.key)
                    }}
                  >
                    Edit
                  </button>
                )
              }
            >
              {editingField === field.key ? (
                <>
                  <textarea
                    className="textarea"
                    style={{ minHeight: 160 }}
                    value={draft}
                    autoFocus
                    aria-label={field.label}
                    onChange={(event) => setDraft(event.target.value)}
                  />
                  <span className="field__hint">{field.hint}</span>
                </>
              ) : dossier[field.key] ? (
                <Markdown text={dossier[field.key]} />
              ) : (
                <p className="small faint mt-0">{field.hint}</p>
              )}
            </Section>
          ))}

          <Section
            title={`Claims and evidence (${claims.length})`}
            description="A claim without evidence is an opinion. Attach the excerpt that supports or undercuts it."
          >
            <div className="row" style={{ marginBottom: 12 }}>
              <input
                className="input"
                style={{ flex: 1, minWidth: 220 }}
                placeholder="State a claim…"
                aria-label="New claim"
                value={claimText}
                onChange={(event) => setClaimText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void addClaim()
                }}
              />
              <select
                className="select"
                style={{ width: 'auto' }}
                aria-label="Claim stance"
                value={claimStance}
                onChange={(event) => setClaimStance(event.target.value)}
              >
                {['bull', 'bear', 'risk', 'question', 'neutral'].map((stance) => (
                  <option key={stance} value={stance}>
                    {titleCase(stance)}
                  </option>
                ))}
              </select>
              <input
                className="input"
                style={{ width: 110 }}
                type="number"
                min={0}
                max={100}
                placeholder="conf %"
                aria-label="Claim confidence"
                value={claimConfidence}
                onChange={(event) => setClaimConfidence(event.target.value)}
              />
              <button type="button" className="btn btn--primary btn--sm" onClick={() => void addClaim()}>
                Add claim
              </button>
            </div>

            {claims.length === 0 ? (
              <EmptyState icon="⚖" title="No claims yet" body="Break the thesis into claims you can attach evidence to." />
            ) : (
              <ul className="list">
                {claims.map((claim) => (
                  <li key={claim.id} className="list__item" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                    <div className="row row--between">
                      <div className="row" style={{ gap: 8 }}>
                        <Badge tone={stanceTone(claim.stance)}>{claim.stance}</Badge>
                        <strong>{claim.text}</strong>
                        {claim.origin === 'generated' ? <GeneratedBadge by={claim.generated_by} /> : null}
                      </div>
                      <div className="btn-group">
                        <span className="xs faint">{confidenceLabel(claim.confidence)}</span>
                        <button type="button" className="btn btn--sm" onClick={() => setEvidenceFor(claim.id)}>
                          Attach evidence
                        </button>
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          onClick={async () => {
                            if (!window.confirm('Delete this claim and its evidence links?')) return
                            await api.deleteClaim(dossierId, claim.id)
                            state.reload()
                          }}
                          aria-label={`Delete claim ${claim.text}`}
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                    {claim.evidence.length > 0 ? (
                      <ul className="stack stack--tight" style={{ listStyle: 'none', padding: '8px 0 0', margin: 0 }}>
                        {claim.evidence.map((evidence) => (
                          <li key={evidence.id}>
                            <blockquote className="quote quote--evidence small">
                              {evidence.text ?? evidence.source_title ?? 'Linked source'}
                            </blockquote>
                            <div className="provenance">
                              <Badge tone={stanceTone(evidence.stance)}>{evidence.stance}</Badge>
                              {evidence.source_id ? (
                                <Link to={`/library/${evidence.source_id}`}>{evidence.source_title}</Link>
                              ) : (
                                <span>{evidence.source_title}</span>
                              )}
                              <button
                                type="button"
                                className="btn btn--ghost btn--sm"
                                onClick={async () => {
                                  await api.deleteClaimEvidence(dossierId, claim.id, evidence.id)
                                  state.reload()
                                }}
                              >
                                remove
                              </button>
                            </div>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <span className="xs faint" style={{ paddingTop: 6 }}>
                        No evidence attached yet.
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section
            title={`Timeline (${timeline.length})`}
            action={
              <button type="button" className="btn btn--sm" onClick={() => setEventOpen(true)}>
                Add event
              </button>
            }
          >
            {timeline.length === 0 ? (
              <EmptyState icon="⏱" title="No events" body="Record the dated events that shaped this subject." />
            ) : (
              <ul className="timeline">
                {timeline.map((event) => (
                  <li key={event.id} className="timeline__item">
                    <div className="row row--between">
                      <div>
                        <div className="timeline__date">
                          {formatDate(event.occurred_on)} · {event.kind}
                        </div>
                        <strong>{event.title}</strong>
                        {event.description ? <p className="small muted">{event.description}</p> : null}
                        {event.source_id ? (
                          <Link className="xs" to={`/library/${event.source_id}`}>
                            {event.source_title}
                          </Link>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={async () => {
                          await api.deleteEvent(dossierId, event.id)
                          state.reload()
                        }}
                        aria-label={`Delete event ${event.title}`}
                      >
                        ✕
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>

        <div className="stack">
          <Section title="Tags">
            <TagEditor
              tags={dossier.tags}
              onSave={async (names) => {
                await api.setDossierTags(dossierId, names)
                state.reload()
              }}
            />
          </Section>

          {Object.entries(SECTION_LABELS).map(([section, label]) => (
            <Section
              key={section}
              title={`${label} (${bySection[section]?.length ?? 0})`}
              action={
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setPickerSection(section)}>
                  Add
                </button>
              }
            >
              {(bySection[section]?.length ?? 0) === 0 ? (
                <p className="small faint mt-0">Nothing here yet.</p>
              ) : (
                <ul className="list">
                  {bySection[section]?.map((item) => (
                    <li key={item.id} className="list__item">
                      <div className="list__main">
                        <Link
                          className="list__title"
                          to={
                            item.target_type === 'source'
                              ? `/library/${item.target_id}`
                              : item.target_type === 'excerpt' && item.source_id
                                ? `/library/${item.source_id}`
                                : item.target_type === 'knowledge'
                                  ? `/knowledge?focus=${item.target_id}`
                                  : item.target_type === 'entity'
                                    ? `/library?entity_id=${item.target_id}`
                                    : `/dossiers/${item.target_id}`
                          }
                        >
                          {item.label}
                        </Link>
                        <span className="list__meta">
                          <Badge>{item.target_type}</Badge>
                          {item.sublabel ? <span>{item.sublabel}</span> : null}
                          {item.note ? <span>· {item.note}</span> : null}
                        </span>
                      </div>
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={async () => {
                          await api.removeDossierItem(dossierId, item.id)
                          state.reload()
                        }}
                        aria-label={`Remove ${item.label}`}
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          ))}

          <Section title={`Related entities (${related_entities.length})`} description="Attached explicitly or mentioned by a linked source.">
            {related_entities.length === 0 ? (
              <p className="small faint mt-0">No entities yet.</p>
            ) : (
              <ul className="list">
                {related_entities.map((entity) => (
                  <li key={entity.id} className="list__item">
                    <div className="list__main">
                      <Link className="list__title" to={`/library?entity_id=${entity.id}`}>
                        {entity.name}
                      </Link>
                      <span className="list__meta">
                        <Badge>{entity.kind}</Badge>
                        <span>{entity.via}</span>
                        {entity.sources ? <span>{entity.sources} source(s)</span> : null}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          {links.length > 0 ? (
            <Section title={`Relationships (${links.length})`}>
              <ul className="list">
                {links.map((link) => (
                  <li key={link.link_id} className="list__item">
                    <div className="list__main">
                      <span className="list__title">{link.label}</span>
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

          <Section title="Open questions helper" description="Deterministic gap analysis; uses a local model only if you enabled one.">
            <button
              type="button"
              className="btn btn--sm"
              onClick={async () => {
                try {
                  setQuestions(await api.runOperation({ operation: 'generate_questions', dossier_id: dossierId }))
                } catch (error) {
                  toast.error((error as Error).message)
                }
              }}
            >
              Find gaps
            </button>
            {questions ? (
              <div className={questions.generated ? 'notice notice--generated' : 'notice'} style={{ marginTop: 10 }}>
                <div className="row">
                  {questions.generated ? <GeneratedBadge by={questions.model} /> : <Badge>deterministic</Badge>}
                </div>
                <p className="small" style={{ marginTop: 6 }}>
                  {questions.notice}
                </p>
                <ul className="small" style={{ paddingLeft: 18, marginBottom: 0 }}>
                  {questions.items.map((item, index) => (
                    <li key={index}>
                      {String(item.text ?? '')}
                      {item.reason ? <span className="faint"> — {String(item.reason)}</span> : null}
                    </li>
                  ))}
                </ul>
                {questions.items.length > 0 ? (
                  <button
                    type="button"
                    className="btn btn--sm"
                    style={{ marginTop: 10 }}
                    onClick={async () => {
                      const appended = [
                        dossier.open_questions,
                        ...questions.items.map((item, index) => `${index + 1}. ${String(item.text ?? '')}`),
                      ]
                        .filter(Boolean)
                        .join('\n')
                      await api.updateDossier(dossierId, { open_questions: appended })
                      toast.success('Appended to open questions (nothing was overwritten).')
                      setQuestions(null)
                      state.reload()
                    }}
                  >
                    Append to open questions
                  </button>
                ) : null}
              </div>
            ) : null}
          </Section>
        </div>
      </div>

      <ObjectPicker
        open={pickerSection !== null}
        onClose={() => setPickerSection(null)}
        onPick={(picked) => void addItem(picked, pickerSection ?? 'sources')}
        title={`Add to ${SECTION_LABELS[pickerSection ?? 'sources']}`}
        types={
          pickerSection === 'evidence'
            ? ['excerpt']
            : pickerSection === 'knowledge' || pickerSection === 'notes'
              ? ['knowledge']
              : pickerSection === 'entities'
                ? ['entity']
                : ['source', 'excerpt', 'knowledge', 'entity']
        }
        excludeIds={items.map((item) => item.target_id)}
      />

      <ObjectPicker
        open={evidenceFor !== null}
        onClose={() => setEvidenceFor(null)}
        onPick={async (picked) => {
          if (!evidenceFor) return
          try {
            await api.addClaimEvidence(dossierId, evidenceFor, {
              excerpt_id: picked.target_type === 'excerpt' ? picked.target_id : undefined,
              source_id: picked.target_type === 'source' ? picked.target_id : undefined,
              stance: 'supports',
            })
            toast.success('Evidence attached.')
            state.reload()
          } catch (error) {
            toast.error((error as Error).message)
          }
        }}
        title="Attach evidence"
        types={['excerpt', 'source']}
      />

      <Modal
        open={eventOpen}
        title="Add timeline event"
        onClose={() => setEventOpen(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setEventOpen(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn--primary" onClick={() => void addEvent()}>
              Add event
            </button>
          </>
        }
      >
        <Field label="Date" htmlFor="event-date">
          <input
            id="event-date"
            className="input"
            type="date"
            value={eventDate}
            onChange={(event) => setEventDate(event.target.value)}
          />
        </Field>
        <Field label="Title" htmlFor="event-title">
          <input
            id="event-title"
            className="input"
            value={eventTitle}
            onChange={(event) => setEventTitle(event.target.value)}
          />
        </Field>
        <Field label="Description" htmlFor="event-description">
          <textarea
            id="event-description"
            className="textarea"
            value={eventDescription}
            onChange={(event) => setEventDescription(event.target.value)}
          />
        </Field>
      </Modal>

      <Modal open={exportPreview !== null} title="Markdown export preview" onClose={() => setExportPreview(null)} wide>
        <pre className="small" style={{ maxHeight: '60vh', overflow: 'auto' }}>
          {exportPreview}
        </pre>
      </Modal>
    </div>
  )
}
