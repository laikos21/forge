import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useToast } from '../components/Toasts'
import { Badge, EmptyState, ErrorState, Loading, Section, Stat } from '../components/ui'
import { api } from '../lib/api'
import { formatDate, formatNumber, relativeTime, statusTone, titleCase } from '../lib/format'
import { useAsync } from '../lib/hooks'

const WINDOWS = [7, 14, 30]

export function ReviewPage() {
  const toast = useToast()
  const [days, setDays] = useState(7)
  const state = useAsync(() => api.review(days), [days])

  if (state.loading && !state.data) return <Loading label="Building your review" rows={6} />
  if (state.error) return <ErrorState message={state.error} onRetry={state.reload} />
  if (!state.data) return null

  const {
    recent_imports,
    unprocessed,
    open_hypotheses,
    recent_dossiers,
    awaiting_review,
    suggestions,
    loose_ends,
    disclaimer,
  } = state.data

  const acceptSuggestion = async (from: { target_type: string; target_id: string }, to: { target_type: string; target_id: string }, action: string) => {
    try {
      if (action === 'link_source_to_dossier') {
        await api.addDossierItem(to.target_id, {
          target_type: from.target_type as 'source',
          target_id: from.target_id,
          section: 'sources',
        })
      } else {
        await api.createLink({
          from_type: from.target_type as 'source',
          from_id: from.target_id,
          to_type: to.target_type as 'dossier',
          to_id: to.target_id,
          relation: 'related_to',
        })
      }
      toast.success('Connection created.')
      state.reload()
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <h1>Daily review</h1>
          <p className="page__subtitle">
            What arrived, what is unfinished, and what overlaps. Everything on this screen is computed from your
            own data with deterministic rules.
          </p>
        </div>
        <div className="page__actions">
          <div className="segmented" role="group" aria-label="Review window">
            {WINDOWS.map((window) => (
              <button key={window} type="button" aria-pressed={days === window} onClick={() => setDays(window)}>
                {window}d
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="grid grid--stats">
        <Stat value={formatNumber(recent_imports.length)} label={`Imported in ${days} days`} />
        <Stat
          value={formatNumber(unprocessed.length)}
          label="Unprocessed sources"
          tone={unprocessed.length ? 'warning' : 'neutral'}
        />
        <Stat
          value={formatNumber(open_hypotheses.length)}
          label="Open hypotheses"
          tone={open_hypotheses.length ? 'accent' : 'neutral'}
        />
        <Stat
          value={formatNumber(awaiting_review.length)}
          label="Rules/decisions to review"
          tone={awaiting_review.length ? 'warning' : 'neutral'}
        />
        <Stat value={formatNumber(loose_ends.excerpts_not_used)} label="Unused excerpts" />
        <Stat value={formatNumber(loose_ends.knowledge_without_evidence)} label="Without evidence" />
      </div>

      <div className="grid grid--2">
        <Section title={`Unprocessed sources (${unprocessed.length})`}>
          {unprocessed.length === 0 ? (
            <EmptyState icon="✓" title="Inbox is clear" body="Everything imported has been reviewed and filed." />
          ) : (
            <ul className="list">
              {unprocessed.map((source) => (
                <li key={source.id} className="list__item">
                  <div className="list__main">
                    <Link className="list__title" to={`/inbox/${source.id}/review`}>
                      {source.title}
                    </Link>
                    <span className="list__meta">
                      <Badge tone={statusTone(source.status)}>{titleCase(source.status)}</Badge>
                      <span>{relativeTime(source.imported_at)}</span>
                      {source.error_message ? <span className="faint">{source.error_message}</span> : null}
                    </span>
                  </div>
                  <Link className="btn btn--sm" to={`/inbox/${source.id}/review`}>
                    Review
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title={`Unresolved hypotheses (${open_hypotheses.length})`}>
          {open_hypotheses.length === 0 ? (
            <EmptyState icon="?" title="No open hypotheses" body="Open one when you have a view you intend to test." />
          ) : (
            <ul className="list">
              {open_hypotheses.map((hypothesis) => (
                <li key={hypothesis.id} className="list__item">
                  <div className="list__main">
                    <Link className="list__title" to={`/knowledge?focus=${hypothesis.id}`}>
                      {hypothesis.title}
                    </Link>
                    <span className="list__meta">
                      <span>{hypothesis.age_days}d old</span>
                      <span>{hypothesis.evidence_count} evidence</span>
                      {hypothesis.confidence !== null ? <span>{hypothesis.confidence}% confidence</span> : null}
                      {hypothesis.evidence_count === 0 ? <Badge tone="warning">no evidence</Badge> : null}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <div className="grid grid--2">
        <Section title={`Rules and decisions to review (${awaiting_review.length})`}>
          {awaiting_review.length === 0 ? (
            <EmptyState icon="⚖" title="Nothing due" body="Rules and decisions appear here as their review date approaches." />
          ) : (
            <ul className="list">
              {awaiting_review.map((item) => (
                <li key={item.id} className="list__item">
                  <div className="list__main">
                    <Link className="list__title" to={`/knowledge?focus=${item.id}`}>
                      {item.title}
                    </Link>
                    <span className="list__meta">
                      <Badge>{item.kind}</Badge>
                      <Badge tone={statusTone(item.status)}>{titleCase(item.status)}</Badge>
                      {item.review_due_on ? <span>due {formatDate(item.review_due_on)}</span> : null}
                      {item.overdue_days && item.overdue_days > 0 ? (
                        <Badge tone="danger">{item.overdue_days}d overdue</Badge>
                      ) : item.due_in_days !== null && item.due_in_days !== undefined ? (
                        <span className="faint">in {item.due_in_days}d</span>
                      ) : null}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title={`Recently modified dossiers (${recent_dossiers.length})`}>
          {recent_dossiers.length === 0 ? (
            <EmptyState icon="❑" title="No dossiers" body="Create one to collect sources around a subject." />
          ) : (
            <ul className="list">
              {recent_dossiers.map((dossier) => (
                <li key={dossier.id} className="list__item">
                  <div className="list__main">
                    <Link className="list__title" to={`/dossiers/${dossier.id}`}>
                      {dossier.title}
                    </Link>
                    <span className="list__meta">
                      <Badge>{titleCase(dossier.subject_kind)}</Badge>
                      <span>{dossier.claims} claims</span>
                      <span>updated {relativeTime(dossier.updated_at)}</span>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <Section title={`Suggested connections (${suggestions.length})`} description={disclaimer}>
        {suggestions.length === 0 ? (
          <EmptyState
            icon="⊹"
            title="No metadata overlaps found"
            body="Suggestions appear when two objects share a tag or an entity and are not connected yet."
          />
        ) : (
          <ul className="list">
            {suggestions.map((suggestion, index) => (
              <li key={index} className="list__item">
                <div className="list__main">
                  <span className="list__title">
                    {suggestion.from.label} <span className="faint">→</span> {suggestion.to.label}
                  </span>
                  <span className="list__meta">
                    <Badge>{suggestion.basis.replace('_', ' ')}</Badge>
                    <span>{suggestion.explanation}</span>
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() => void acceptSuggestion(suggestion.from, suggestion.to, suggestion.suggested_action)}
                >
                  Connect
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={`Recently imported (${recent_imports.length})`}>
        {recent_imports.length === 0 ? (
          <EmptyState icon="⇩" title="Nothing imported in this window" body="Widen the window or import new material." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Type</th>
                  <th className="table__num">Words</th>
                  <th>Status</th>
                  <th>Imported</th>
                </tr>
              </thead>
              <tbody>
                {recent_imports.map((source) => (
                  <tr key={source.id}>
                    <td>
                      <Link to={`/library/${source.id}`}>{source.title}</Link>
                    </td>
                    <td>{titleCase(source.kind)}</td>
                    <td className="table__num">{formatNumber(source.word_count)}</td>
                    <td>
                      <Badge tone={statusTone(source.status)}>{titleCase(source.status)}</Badge>
                    </td>
                    <td className="muted nowrap">{relativeTime(source.imported_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  )
}
