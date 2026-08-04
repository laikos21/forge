import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Modal } from '../components/Modal'
import { ObjectPicker } from '../components/ObjectPicker'
import { useToast } from '../components/Toasts'
import { Badge, DemoBadge, EmptyState, ErrorState, Field, Loading, Section } from '../components/ui'
import { api } from '../lib/api'
import { titleCase } from '../lib/format'
import { useAsync } from '../lib/hooks'

export function ComparisonPage() {
  const { comparisonId = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const state = useAsync(() => api.comparison(comparisonId), [comparisonId])
  const [pickerOpen, setPickerOpen] = useState(false)
  const [dimensionOpen, setDimensionOpen] = useState(false)
  const [dimensionName, setDimensionName] = useState('')
  const [dimensionKind, setDimensionKind] = useState('text')
  const [dimensionUnit, setDimensionUnit] = useState('')
  const [higherIsBetter, setHigherIsBetter] = useState(true)

  if (state.loading && !state.data) return <Loading label="Loading comparison" rows={5} />
  if (state.error) return <ErrorState message={state.error} onRetry={state.reload} />
  if (!state.data) return null

  const comparison = state.data

  const saveCell = async (subjectId: string, dimensionId: string, kind: string, raw: string) => {
    const payload: Record<string, unknown> = { subject_id: subjectId, dimension_id: dimensionId }
    if (kind === 'number' || kind === 'rating') {
      payload.numeric_value = raw.trim() === '' ? null : raw.trim()
    } else if (kind === 'boolean') {
      payload.boolean_value = raw === '' ? null : raw === 'yes'
    } else {
      payload.text_value = raw
    }
    try {
      const updated = await api.setCell(comparisonId, payload)
      state.setData(updated)
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const addDimension = async () => {
    if (!dimensionName.trim()) return
    try {
      const updated = await api.addDimension(comparisonId, {
        name: dimensionName.trim(),
        kind: dimensionKind,
        unit: dimensionUnit || null,
        higher_is_better: higherIsBetter,
      })
      state.setData(updated)
      setDimensionOpen(false)
      setDimensionName('')
      setDimensionUnit('')
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <div className="row" style={{ gap: 8 }}>
            <Badge>{titleCase(comparison.subject_type)}</Badge>
            {comparison.is_demo ? <DemoBadge /> : null}
          </div>
          <h1>{comparison.title}</h1>
          {comparison.description ? <p className="page__subtitle">{comparison.description}</p> : null}
        </div>
        <div className="page__actions">
          <button type="button" className="btn" onClick={() => setPickerOpen(true)}>
            Add subject
          </button>
          <button type="button" className="btn" onClick={() => setDimensionOpen(true)}>
            Add dimension
          </button>
          <a className="btn" href={api.comparisonMarkdownUrl(comparisonId)}>
            Export Markdown
          </a>
          <button
            type="button"
            className="btn btn--danger"
            onClick={async () => {
              if (!window.confirm('Delete this comparison?')) return
              await api.deleteComparison(comparisonId)
              navigate('/compare')
            }}
          >
            Delete
          </button>
        </div>
      </header>

      {comparison.subjects.length === 0 || comparison.dimensions.length === 0 ? (
        <EmptyState
          icon="⇹"
          title="Add subjects and dimensions"
          body="A comparison needs at least two subjects and one dimension before the grid becomes useful."
          action={
            <div className="btn-group">
              <button type="button" className="btn btn--primary" onClick={() => setPickerOpen(true)}>
                Add a subject
              </button>
              <button type="button" className="btn" onClick={() => setDimensionOpen(true)}>
                Add a dimension
              </button>
            </div>
          }
        />
      ) : (
        <Section title="Matrix" description="Cells save when they lose focus. Numeric columns are ranked; the best value is highlighted.">
          <div className="table-wrap">
            <table className="matrix">
              <thead>
                <tr>
                  <th style={{ minWidth: 180 }}>Dimension</th>
                  {comparison.subjects.map((subject) => (
                    <th key={subject.id}>
                      <div className="row row--between">
                        <span>{subject.label}</span>
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          aria-label={`Remove ${subject.label}`}
                          onClick={async () => {
                            const updated = await api.removeSubject(comparisonId, subject.id)
                            state.setData(updated)
                          }}
                        >
                          ✕
                        </button>
                      </div>
                      <span className="xs faint">{subject.sublabel || subject.target_type}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {comparison.dimensions.map((dimension) => {
                  const ranking = comparison.rankings[dimension.id] ?? []
                  return (
                    <tr key={dimension.id}>
                      <th scope="row">
                        <div className="row row--between">
                          <span>{dimension.name}</span>
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            aria-label={`Remove ${dimension.name}`}
                            onClick={async () => {
                              const updated = await api.removeDimension(comparisonId, dimension.id)
                              state.setData(updated)
                            }}
                          >
                            ✕
                          </button>
                        </div>
                        <span className="xs faint">
                          {dimension.kind}
                          {dimension.unit ? ` · ${dimension.unit}` : ''}
                          {dimension.kind === 'number' || dimension.kind === 'rating'
                            ? dimension.higher_is_better
                              ? ' · higher is better'
                              : ' · lower is better'
                            : ''}
                        </span>
                      </th>
                      {comparison.subjects.map((subject) => {
                        const cell = comparison.cells[`${subject.id}:${dimension.id}`]
                        const isBest = ranking[0] === subject.id
                        const value =
                          dimension.kind === 'number' || dimension.kind === 'rating'
                            ? (cell?.numeric_value ?? '')
                            : dimension.kind === 'boolean'
                              ? cell?.boolean_value === null || cell?.boolean_value === undefined
                                ? ''
                                : cell.boolean_value
                                  ? 'yes'
                                  : 'no'
                              : (cell?.text_value ?? '')
                        return (
                          <td key={subject.id} className={isBest ? 'rank-1' : undefined}>
                            {dimension.kind === 'boolean' ? (
                              <select
                                className="select"
                                aria-label={`${dimension.name} for ${subject.label}`}
                                defaultValue={String(value)}
                                onChange={(event) =>
                                  void saveCell(subject.id, dimension.id, dimension.kind, event.target.value)
                                }
                              >
                                <option value="">—</option>
                                <option value="yes">yes</option>
                                <option value="no">no</option>
                              </select>
                            ) : dimension.kind === 'number' || dimension.kind === 'rating' ? (
                              <input
                                className="input"
                                inputMode="decimal"
                                aria-label={`${dimension.name} for ${subject.label}`}
                                defaultValue={String(value)}
                                onBlur={(event) =>
                                  void saveCell(subject.id, dimension.id, dimension.kind, event.target.value)
                                }
                              />
                            ) : (
                              <textarea
                                className="textarea"
                                style={{ minHeight: 58, fontFamily: 'var(--font)' }}
                                aria-label={`${dimension.name} for ${subject.label}`}
                                defaultValue={String(value)}
                                onBlur={(event) =>
                                  void saveCell(subject.id, dimension.id, dimension.kind, event.target.value)
                                }
                              />
                            )}
                            {cell?.origin === 'generated' ? <Badge tone="generated">generated</Badge> : null}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      <ObjectPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={async (picked) => {
          try {
            const updated = await api.addSubject(comparisonId, {
              target_type: picked.target_type,
              target_id: picked.target_id,
              label: picked.label,
            })
            state.setData(updated)
          } catch (error) {
            toast.error((error as Error).message)
          }
        }}
        title="Add a subject"
        types={[comparison.subject_type]}
        excludeIds={comparison.subjects.map((subject) => subject.target_id)}
      />

      <Modal
        open={dimensionOpen}
        title="Add dimension"
        onClose={() => setDimensionOpen(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setDimensionOpen(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn--primary" onClick={() => void addDimension()}>
              Add
            </button>
          </>
        }
      >
        <Field label="Name" htmlFor="dimension-name">
          <input
            id="dimension-name"
            className="input"
            autoFocus
            value={dimensionName}
            onChange={(event) => setDimensionName(event.target.value)}
          />
        </Field>
        <Field label="Kind" htmlFor="dimension-kind">
          <select
            id="dimension-kind"
            className="select"
            value={dimensionKind}
            onChange={(event) => setDimensionKind(event.target.value)}
          >
            <option value="text">Text</option>
            <option value="number">Number</option>
            <option value="rating">Rating</option>
            <option value="boolean">Yes / no</option>
          </select>
        </Field>
        <Field label="Unit (optional)" htmlFor="dimension-unit">
          <input
            id="dimension-unit"
            className="input"
            value={dimensionUnit}
            onChange={(event) => setDimensionUnit(event.target.value)}
            placeholder="%, USD, x"
          />
        </Field>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={higherIsBetter}
            onChange={(event) => setHigherIsBetter(event.target.checked)}
          />
          Higher values are better (used for ranking)
        </label>
      </Modal>
    </div>
  )
}
