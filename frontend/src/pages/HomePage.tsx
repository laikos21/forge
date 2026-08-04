import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, Loading, Section, Stat } from '../components/ui'
import { useToast } from '../components/Toasts'
import { api } from '../lib/api'
import { formatNumber, relativeTime, SOURCE_KIND_LABELS, titleCase } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { SourceKind } from '../lib/types'

export function HomePage() {
  const toast = useToast()
  const state = useAsync(() => api.home(), [])

  if (state.loading && !state.data) return <Loading label="Loading your workspace" rows={5} />
  if (state.error) return <ErrorState message={state.error} onRetry={state.reload} />
  if (!state.data) return null

  const { stats, recent_sources, recent_dossiers, unprocessed, loose_ends } = state.data
  const isEmpty = stats.sources === 0 && stats.dossiers === 0 && stats.knowledge === 0

  const seed = async () => {
    try {
      toast.info('Loading demonstration data…')
      const result = await api.seed(false)
      if (result.status === 'skipped') toast.info(String(result.reason))
      else toast.success('Demonstration data loaded.')
      state.reload()
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <h1>Home</h1>
          <p className="page__subtitle">
            Everything in FORGE lives on this machine: SQLite for storage and search, the local filesystem for
            your original files. No account, no API key, no network required.
          </p>
        </div>
        <div className="page__actions">
          <Link className="btn btn--primary" to="/inbox">
            Import material
          </Link>
          <Link className="btn" to="/review">
            Daily review
          </Link>
        </div>
      </header>

      {isEmpty ? (
        <EmptyState
          icon="◆"
          title="Your knowledge base is empty"
          body={
            <>
              Drop a PDF, paste a transcript, or load the worked example to see how sources, excerpts, knowledge
              objects and dossiers fit together. Demonstration content is clearly labelled and removable in one
              click.
            </>
          }
          action={
            <div className="btn-group">
              <Link className="btn btn--primary" to="/inbox">
                Go to the Inbox
              </Link>
              <button type="button" className="btn" onClick={() => void seed()}>
                Load demonstration data
              </button>
            </div>
          }
        />
      ) : null}

      <div className="grid grid--stats">
        <Stat value={formatNumber(stats.sources)} label="Sources" />
        <Stat value={formatNumber(stats.excerpts)} label="Excerpts" />
        <Stat value={formatNumber(stats.knowledge)} label="Knowledge objects" />
        <Stat value={formatNumber(stats.dossiers)} label="Dossiers" />
        <Stat value={formatNumber(stats.entities)} label="Entities" />
        <Stat
          value={formatNumber(stats.needs_review)}
          label="Awaiting review"
          tone={stats.needs_review > 0 ? 'warning' : 'neutral'}
        />
        {stats.errors > 0 ? <Stat value={formatNumber(stats.errors)} label="Import errors" tone="danger" /> : null}
        <Stat value={formatNumber(stats.words_indexed)} label="Words indexed" />
      </div>

      <div className="grid grid--2">
        <Section
          title="Recently imported"
          action={
            <Link className="btn btn--ghost btn--sm" to="/library">
              Open library
            </Link>
          }
        >
          {recent_sources.length === 0 ? (
            <p className="small muted mt-0">Nothing imported yet.</p>
          ) : (
            <ul className="list">
              {recent_sources.map((source) => (
                <li key={source.id} className="list__item">
                  <div className="list__main">
                    <Link className="list__title" to={`/library/${source.id}`}>
                      {source.title}
                    </Link>
                    <span className="list__meta">
                      <span className="badge">{SOURCE_KIND_LABELS[source.kind as SourceKind] ?? source.kind}</span>
                      <span>{formatNumber(source.word_count)} words</span>
                      <span>{relativeTime(source.imported_at)}</span>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section
          title="Active dossiers"
          action={
            <Link className="btn btn--ghost btn--sm" to="/dossiers">
              All dossiers
            </Link>
          }
        >
          {recent_dossiers.length === 0 ? (
            <p className="small muted mt-0">No dossiers yet. Create one from any source or excerpt.</p>
          ) : (
            <ul className="list">
              {recent_dossiers.map((dossier) => (
                <li key={dossier.id} className="list__item">
                  <div className="list__main">
                    <Link className="list__title" to={`/dossiers/${dossier.id}`}>
                      {dossier.title}
                    </Link>
                    <span className="list__meta">
                      <span className="badge">{titleCase(dossier.subject_kind)}</span>
                      <span>{dossier.claims} claims</span>
                      <span>{dossier.items} linked items</span>
                      <span>updated {relativeTime(dossier.updated_at)}</span>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <div className="grid grid--2">
        <Section title="Needs your attention">
          {unprocessed.length === 0 ? (
            <p className="small muted mt-0">The inbox is clear.</p>
          ) : (
            <ul className="list">
              {unprocessed.map((source) => (
                <li key={source.id} className="list__item">
                  <div className="list__main">
                    <Link className="list__title" to={`/inbox/${source.id}/review`}>
                      {source.title}
                    </Link>
                    <span className="list__meta">
                      <span className={source.status === 'error' ? 'badge badge--danger' : 'badge badge--warning'}>
                        {titleCase(source.status)}
                      </span>
                      {source.error_message ? <span>{source.error_message}</span> : null}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Loose ends" description="Deterministic counts, not suggestions.">
          <ul className="list">
            <li className="list__item">
              <div className="list__main">
                <span className="list__title">{formatNumber(loose_ends.sources_without_tags)} sources without tags</span>
                <span className="list__meta">Tagging is what makes the library filterable later.</span>
              </div>
              <Link className="btn btn--sm" to="/library?sort=imported_desc">
                Open
              </Link>
            </li>
            <li className="list__item">
              <div className="list__main">
                <span className="list__title">{formatNumber(loose_ends.excerpts_not_used)} excerpts not used anywhere</span>
                <span className="list__meta">Promote them to insights or attach them to a dossier.</span>
              </div>
              <Link className="btn btn--sm" to="/knowledge?tab=excerpts">
                Open
              </Link>
            </li>
            <li className="list__item">
              <div className="list__main">
                <span className="list__title">
                  {formatNumber(loose_ends.knowledge_without_evidence)} insights or hypotheses without evidence
                </span>
                <span className="list__meta">An unsupported claim is a note, not a finding.</span>
              </div>
              <Link className="btn btn--sm" to="/knowledge?has_evidence=false">
                Open
              </Link>
            </li>
          </ul>
        </Section>
      </div>
    </div>
  )
}
