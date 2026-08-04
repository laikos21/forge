import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useToast } from '../components/Toasts'
import { Badge, ErrorState, Field, Loading, Section } from '../components/ui'
import { api } from '../lib/api'
import { formatNumber, parseTagInput, SOURCE_KIND_LABELS } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { EntityCandidate, SourceKind } from '../lib/types'

const CONFIDENCE_TONE: Record<string, 'success' | 'warning' | 'neutral'> = {
  high: 'success',
  medium: 'warning',
  low: 'neutral',
}

/**
 * The review screen: the step between "extracted" and "part of the library".
 * Detected values are shown as *proposals* - nothing is written to the source
 * until the user confirms it here.
 */
export function ReviewSourcePage() {
  const { sourceId = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const state = useAsync(() => api.reviewPayload(sourceId), [sourceId])

  const [title, setTitle] = useState('')
  const [author, setAuthor] = useState('')
  const [publisher, setPublisher] = useState('')
  const [publishedOn, setPublishedOn] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [language, setLanguage] = useState('')
  const [notes, setNotes] = useState('')
  const [tags, setTags] = useState('')
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!state.data) return
    const { source, detected, entity_candidates } = state.data
    setTitle(source.title)
    setAuthor(source.author ?? (typeof detected.author === 'string' ? detected.author : '') ?? '')
    setPublisher(source.publisher ?? '')
    setPublishedOn(source.published_on ?? (typeof detected.published_on === 'string' ? detected.published_on : '') ?? '')
    setSourceUrl(source.source_url ?? '')
    setLanguage(source.language ?? (typeof detected.language === 'string' ? detected.language : '') ?? '')
    setNotes('')
    setTags(source.tags.map((tag) => tag.name).join(', '))
    const preset: Record<string, boolean> = {}
    for (const candidate of entity_candidates) {
      preset[`${candidate.kind}:${candidate.name}`] = candidate.confidence === 'high' || Boolean(candidate.existing_id)
    }
    setSelected(preset)
  }, [state.data])

  if (state.loading && !state.data) return <Loading label="Loading review" rows={6} />
  if (state.error) return <ErrorState message={state.error} onRetry={state.reload} />
  if (!state.data) return null

  const { source, detected, entity_candidates, warnings, preview, documents } = state.data
  const keywords = Array.isArray(detected.keywords) ? (detected.keywords as string[]) : []
  const datesInText = Array.isArray(detected.dates_in_text) ? (detected.dates_in_text as string[]) : []

  const submit = async () => {
    setSaving(true)
    try {
      const confirmed: EntityCandidate[] = entity_candidates.filter(
        (candidate) => selected[`${candidate.kind}:${candidate.name}`],
      )
      await api.submitReview(sourceId, {
        title: title.trim() || source.title,
        author: author.trim() || null,
        publisher: publisher.trim() || null,
        published_on: publishedOn || null,
        source_url: sourceUrl.trim() || null,
        language: language.trim() || null,
        review_notes: notes.trim() || null,
        tags: parseTagInput(tags),
        confirmed_entities: confirmed.map((candidate) => ({
          kind: candidate.kind,
          name: candidate.name,
          count: candidate.count,
          detector: candidate.detector,
          confidence: candidate.confidence,
        })),
      })
      toast.success('Source reviewed and filed in the library.')
      navigate(`/library/${sourceId}`)
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <h1>Review before filing</h1>
          <p className="page__subtitle">
            FORGE proposes metadata and entities it detected with deterministic rules. Confirm what is correct —
            nothing detected is attached to the source until you do.
          </p>
        </div>
        <div className="page__actions">
          <Link className="btn btn--ghost" to="/inbox">
            Back to inbox
          </Link>
          <button type="button" className="btn btn--primary" onClick={() => void submit()} disabled={saving}>
            {saving ? 'Saving…' : 'Confirm and file'}
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

      <div className="split">
        <div className="stack">
          <Section title="Metadata">
            <div className="field-grid">
              <Field label="Title" htmlFor="review-title">
                <input id="review-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
              </Field>
              <Field
                label="Author"
                htmlFor="review-author"
                hint={typeof detected.author === 'string' && detected.author ? `Detected: ${detected.author}` : undefined}
              >
                <input id="review-author" className="input" value={author} onChange={(e) => setAuthor(e.target.value)} />
              </Field>
              <Field label="Publisher" htmlFor="review-publisher">
                <input
                  id="review-publisher"
                  className="input"
                  value={publisher}
                  onChange={(e) => setPublisher(e.target.value)}
                />
              </Field>
              <Field
                label="Published on"
                htmlFor="review-published"
                hint={datesInText.length ? `Dates found in the text: ${datesInText.slice(0, 3).join(', ')}` : undefined}
              >
                <input
                  id="review-published"
                  className="input"
                  type="date"
                  value={publishedOn}
                  onChange={(e) => setPublishedOn(e.target.value)}
                />
              </Field>
              <Field label="Source URL" htmlFor="review-url">
                <input id="review-url" className="input" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} />
              </Field>
              <Field label="Language" htmlFor="review-language" hint="Detected from stopword frequency.">
                <input
                  id="review-language"
                  className="input"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  maxLength={8}
                />
              </Field>
            </div>
            <Field label="Tags" htmlFor="review-tags" hint="Comma separated. Tags drive library filters and review suggestions.">
              <input id="review-tags" className="input" value={tags} onChange={(e) => setTags(e.target.value)} />
            </Field>
            {keywords.length > 0 ? (
              <div className="stack stack--tight">
                <span className="field__label">Suggested from keyword frequency</span>
                <div className="chip-row">
                  {keywords.map((keyword) => (
                    <button
                      key={keyword}
                      type="button"
                      className="chip"
                      onClick={() => setTags((current) => (current ? `${current}, ${keyword}` : keyword))}
                    >
                      + {keyword}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            <Field label="Review note (optional)" htmlFor="review-note">
              <textarea
                id="review-note"
                className="textarea"
                style={{ minHeight: 70 }}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Why you kept this, what to check later…"
              />
            </Field>
          </Section>

          <Section
            title={`Detected entities (${entity_candidates.length})`}
            description="Pattern-based detection: $TICKER symbols, legal suffixes, bylines and keyword frequency. Confidence is stated, never hidden."
          >
            {entity_candidates.length === 0 ? (
              <p className="small muted mt-0">No entities detected. You can add them from the source page later.</p>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: 40 }}>Use</th>
                      <th>Name</th>
                      <th>Type</th>
                      <th>Confidence</th>
                      <th className="table__num">Mentions</th>
                      <th>Detector</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entity_candidates.map((candidate) => {
                      const key = `${candidate.kind}:${candidate.name}`
                      return (
                        <tr key={key}>
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Confirm ${candidate.name}`}
                              checked={Boolean(selected[key])}
                              onChange={(event) =>
                                setSelected((current) => ({ ...current, [key]: event.target.checked }))
                              }
                            />
                          </td>
                          <td>
                            {candidate.name}
                            {candidate.existing_id ? (
                              <span className="xs faint"> · already in FORGE</span>
                            ) : null}
                          </td>
                          <td>
                            <Badge>{candidate.kind}</Badge>
                          </td>
                          <td>
                            <Badge tone={CONFIDENCE_TONE[candidate.confidence] ?? 'neutral'}>
                              {candidate.confidence}
                            </Badge>
                          </td>
                          <td className="table__num">{candidate.count}</td>
                          <td className="xs faint mono">{candidate.detector}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </div>

        <div className="stack">
          <Section title="Extraction">
            <ul className="list">
              <li className="list__item">
                <div className="list__main">
                  <span className="list__title">{SOURCE_KIND_LABELS[source.kind as SourceKind] ?? source.kind}</span>
                  <span className="list__meta">
                    <span className="mono xs">{source.extraction_method}</span>
                  </span>
                </div>
              </li>
              <li className="list__item">
                <div className="list__main">
                  <span className="list__title">{formatNumber(source.word_count)} words</span>
                  <span className="list__meta">
                    {formatNumber(source.char_count)} characters · {documents} structural units
                  </span>
                </div>
              </li>
              <li className="list__item">
                <div className="list__main">
                  <span className="list__title">Content hash</span>
                  <span className="list__meta mono xs">{source.content_hash.slice(0, 24)}…</span>
                </div>
              </li>
              {source.original_filename ? (
                <li className="list__item">
                  <div className="list__main">
                    <span className="list__title">Original preserved</span>
                    <span className="list__meta">{source.original_filename}</span>
                  </div>
                  <a className="btn btn--sm" href={api.fileUrl(source.id)} target="_blank" rel="noreferrer">
                    Open
                  </a>
                </li>
              ) : null}
            </ul>
          </Section>

          <Section title="Text preview">
            <div className="reader" style={{ maxHeight: '38vh' }}>
              <pre className="reader__text">{preview}</pre>
            </div>
          </Section>
        </div>
      </div>
    </div>
  )
}
