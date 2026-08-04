import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Modal } from '../components/Modal'
import { useToast } from '../components/Toasts'
import { Badge, DemoBadge, EmptyState, ErrorState, Field, Loading } from '../components/ui'
import { api } from '../lib/api'
import { parseTagInput, relativeTime, statusTone, titleCase, truncate } from '../lib/format'
import { useAsync } from '../lib/hooks'

const SUBJECTS = ['company', 'industry', 'setup', 'theme', 'project', 'person', 'other']
const STATUSES = ['active', 'watching', 'archived']

export function DossiersPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const [creating, setCreating] = useState(params.get('new') === '1')
  const [subjectFilter, setSubjectFilter] = useState<string[]>([])
  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [query, setQuery] = useState('')

  const [title, setTitle] = useState('')
  const [subjectKind, setSubjectKind] = useState('company')
  const [overview, setOverview] = useState('')
  const [tags, setTags] = useState('')

  const dossiers = useAsync(
    () => api.dossiers({ q: query || undefined, subject_kind: subjectFilter, status: statusFilter }),
    [query, subjectFilter.join(','), statusFilter.join(',')],
  )

  useEffect(() => {
    if (params.get('new') === '1') {
      setCreating(true)
      params.delete('new')
      setParams(params, { replace: true })
    }
  }, [params, setParams])

  const create = async () => {
    if (!title.trim()) {
      toast.error('A dossier needs a title.')
      return
    }
    try {
      const created = await api.createDossier({
        title: title.trim(),
        subject_kind: subjectKind,
        overview,
        tags: parseTagInput(tags),
      })
      toast.success('Dossier created.')
      setCreating(false)
      setTitle('')
      setOverview('')
      setTags('')
      dossiers.reload()
      navigate(`/dossiers/${created.id}`)
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const items = dossiers.data?.items ?? []

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <h1>Dossiers</h1>
          <p className="page__subtitle">
            A dossier is a research workspace for one subject: a stock, an industry, a trading setup, a theme, a
            software project or a mentor. It holds the sources, the evidence, the cases for and against, and the
            questions still open.
          </p>
        </div>
        <div className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => setCreating(true)}>
            New dossier
          </button>
        </div>
      </header>

      <div className="row">
        <input
          className="input"
          style={{ maxWidth: 320 }}
          placeholder="Filter by title or overview…"
          aria-label="Filter dossiers"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="chip-row">
          {SUBJECTS.map((subject) => (
            <button
              key={subject}
              type="button"
              className="chip"
              aria-pressed={subjectFilter.includes(subject)}
              onClick={() =>
                setSubjectFilter((current) =>
                  current.includes(subject) ? current.filter((item) => item !== subject) : [...current, subject],
                )
              }
            >
              {titleCase(subject)}
            </button>
          ))}
        </div>
        <div className="chip-row">
          {STATUSES.map((status) => (
            <button
              key={status}
              type="button"
              className="chip"
              aria-pressed={statusFilter.includes(status)}
              onClick={() =>
                setStatusFilter((current) =>
                  current.includes(status) ? current.filter((item) => item !== status) : [...current, status],
                )
              }
            >
              {titleCase(status)}
            </button>
          ))}
        </div>
      </div>

      {dossiers.loading && !dossiers.data ? <Loading label="Loading dossiers" rows={4} /> : null}
      {dossiers.error ? <ErrorState message={dossiers.error} onRetry={dossiers.reload} /> : null}

      {!dossiers.loading && items.length === 0 ? (
        <EmptyState
          icon="❑"
          title="No dossiers yet"
          body="Create one for the next company, setup or theme you are working on, then attach sources and excerpts to it as you read."
          action={
            <button type="button" className="btn btn--primary" onClick={() => setCreating(true)}>
              Create the first dossier
            </button>
          }
        />
      ) : null}

      <div className="grid grid--cards">
        {items.map((dossier) => (
          <Link key={dossier.id} className="source-card" to={`/dossiers/${dossier.id}`}>
            <div className="row" style={{ gap: 8 }}>
              <Badge>{titleCase(dossier.subject_kind)}</Badge>
              <Badge tone={statusTone(dossier.status)}>{titleCase(dossier.status)}</Badge>
              {dossier.is_demo ? <DemoBadge /> : null}
            </div>
            <div className="source-card__title">{dossier.title}</div>
            {dossier.overview ? <p className="source-card__summary">{truncate(dossier.overview, 170)}</p> : null}
            <div className="source-card__foot">
              <span>
                {dossier.counts.sources ?? 0} sources · {dossier.counts.claims ?? 0} claims
              </span>
              <span>updated {relativeTime(dossier.updated_at)}</span>
            </div>
            {dossier.tags.length > 0 ? (
              <div className="tag-list">
                {dossier.tags.slice(0, 4).map((tag) => (
                  <span key={tag.id} className="tag">
                    {tag.name}
                  </span>
                ))}
              </div>
            ) : null}
          </Link>
        ))}
      </div>

      <Modal
        open={creating}
        title="New dossier"
        onClose={() => setCreating(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn--primary" onClick={() => void create()}>
              Create dossier
            </button>
          </>
        }
      >
        <Field label="Title" htmlFor="dossier-title">
          <input
            id="dossier-title"
            className="input"
            value={title}
            autoFocus
            onChange={(event) => setTitle(event.target.value)}
            placeholder="e.g. Helios Semiconductor (HLSX)"
          />
        </Field>
        <Field label="Subject" htmlFor="dossier-subject">
          <select
            id="dossier-subject"
            className="select"
            value={subjectKind}
            onChange={(event) => setSubjectKind(event.target.value)}
          >
            {SUBJECTS.map((subject) => (
              <option key={subject} value={subject}>
                {titleCase(subject)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Overview" htmlFor="dossier-overview" hint="Markdown supported. What is this dossier for?">
          <textarea
            id="dossier-overview"
            className="textarea"
            value={overview}
            onChange={(event) => setOverview(event.target.value)}
          />
        </Field>
        <Field label="Tags" htmlFor="dossier-tags" hint="Comma separated.">
          <input id="dossier-tags" className="input" value={tags} onChange={(event) => setTags(event.target.value)} />
        </Field>
      </Modal>
    </div>
  )
}
