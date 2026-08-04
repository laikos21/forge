import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Modal } from '../components/Modal'
import { useToast } from '../components/Toasts'
import { Badge, DemoBadge, EmptyState, ErrorState, Field, Loading } from '../components/ui'
import { api } from '../lib/api'
import { relativeTime, titleCase } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { TargetType } from '../lib/types'

const SUBJECT_TYPES: TargetType[] = ['entity', 'source', 'knowledge', 'dossier']

export function ComparePage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const comparisons = useAsync(() => api.comparisons(), [])
  const [creating, setCreating] = useState(params.get('new') === '1')
  const [title, setTitle] = useState('')
  const [subjectType, setSubjectType] = useState<TargetType>('entity')
  const [description, setDescription] = useState('')
  const [dimensions, setDimensions] = useState('Thesis, Risk, Evidence in FORGE')

  useEffect(() => {
    if (params.get('new') === '1') {
      setCreating(true)
      params.delete('new')
      setParams(params, { replace: true })
    }
  }, [params, setParams])

  const create = async () => {
    if (!title.trim()) {
      toast.error('A comparison needs a title.')
      return
    }
    try {
      const created = await api.createComparison({
        title: title.trim(),
        subject_type: subjectType,
        description: description || null,
        dimensions: dimensions
          .split(',')
          .map((dimension) => dimension.trim())
          .filter(Boolean),
      })
      toast.success('Comparison created.')
      setCreating(false)
      setTitle('')
      navigate(`/compare/${created.id}`)
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const items = comparisons.data?.items ?? []

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <h1>Comparison workspace</h1>
          <p className="page__subtitle">
            Put two or more companies, sources, hypotheses or dossiers side by side across dimensions you define.
            Numeric dimensions are ranked exactly (decimal, not floating point); text dimensions stay text.
          </p>
        </div>
        <div className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => setCreating(true)}>
            New comparison
          </button>
        </div>
      </header>

      {comparisons.loading && !comparisons.data ? <Loading label="Loading comparisons" rows={3} /> : null}
      {comparisons.error ? <ErrorState message={comparisons.error} onRetry={comparisons.reload} /> : null}

      {!comparisons.loading && items.length === 0 ? (
        <EmptyState
          icon="⇹"
          title="No comparisons yet"
          body="Create one to compare candidates on the dimensions that actually drive your decision."
          action={
            <button type="button" className="btn btn--primary" onClick={() => setCreating(true)}>
              Create a comparison
            </button>
          }
        />
      ) : null}

      <div className="grid grid--cards">
        {items.map((comparison) => (
          <Link key={comparison.id} className="source-card" to={`/compare/${comparison.id}`}>
            <div className="row" style={{ gap: 8 }}>
              <Badge>{titleCase(comparison.subject_type)}</Badge>
              {comparison.is_demo ? <DemoBadge /> : null}
            </div>
            <div className="source-card__title">{comparison.title}</div>
            {comparison.description ? <p className="source-card__summary">{comparison.description}</p> : null}
            <div className="source-card__foot">
              <span>
                {comparison.subject_count} subjects · {comparison.dimension_count} dimensions
              </span>
              <span>{relativeTime(comparison.updated_at)}</span>
            </div>
          </Link>
        ))}
      </div>

      <Modal
        open={creating}
        title="New comparison"
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
        <Field label="Title" htmlFor="comparison-title">
          <input
            id="comparison-title"
            className="input"
            autoFocus
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="e.g. Open positions - risk and thesis"
          />
        </Field>
        <Field label="Subjects are" htmlFor="comparison-type">
          <select
            id="comparison-type"
            className="select"
            value={subjectType}
            onChange={(event) => setSubjectType(event.target.value as TargetType)}
          >
            {SUBJECT_TYPES.map((type) => (
              <option key={type} value={type}>
                {titleCase(type)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Description" htmlFor="comparison-description">
          <textarea
            id="comparison-description"
            className="textarea"
            style={{ minHeight: 70 }}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <Field label="Dimensions" htmlFor="comparison-dimensions" hint="Comma separated. You can add more later.">
          <input
            id="comparison-dimensions"
            className="input"
            value={dimensions}
            onChange={(event) => setDimensions(event.target.value)}
          />
        </Field>
      </Modal>
    </div>
  )
}
