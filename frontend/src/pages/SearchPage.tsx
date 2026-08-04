import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Badge, EmptyState, ErrorState, Highlighted, Loading, Section, Segmented } from '../components/ui'
import { api } from '../lib/api'
import { formatNumber, titleCase } from '../lib/format'
import { useAsync, useDebounced } from '../lib/hooks'
import type { SearchHit, TargetType } from '../lib/types'

const TYPES: Array<{ value: TargetType; label: string }> = [
  { value: 'source', label: 'Sources' },
  { value: 'excerpt', label: 'Excerpts' },
  { value: 'knowledge', label: 'Knowledge' },
  { value: 'dossier', label: 'Dossiers' },
  { value: 'entity', label: 'Entities' },
]

function hitLink(hit: SearchHit): string {
  switch (hit.ref_type) {
    case 'source':
      return `/library/${hit.ref_id}`
    case 'excerpt':
      return hit.source_id ? `/library/${hit.source_id}` : '/library'
    case 'dossier':
      return `/dossiers/${hit.ref_id}`
    case 'knowledge':
      return `/knowledge?focus=${hit.ref_id}`
    case 'entity':
      return `/library?entity_id=${hit.ref_id}`
    default:
      return '/search'
  }
}

function HitRow({ hit }: { hit: SearchHit }) {
  return (
    <article className="hit">
      <div className="row" style={{ gap: 8 }}>
        <Badge>{hit.ref_type}</Badge>
        {hit.kind ? <span className="xs faint">{hit.kind}</span> : null}
        {hit.origin === 'generated' ? <Badge tone="generated">generated</Badge> : null}
      </div>
      <Link className="hit__title" to={hitLink(hit)}>
        {hit.title || '(untitled)'}
      </Link>
      <p className="hit__snippet">
        <Highlighted snippet={hit.snippet} />
      </p>
      <div className="provenance">
        {hit.provenance ? (
          <>
            <Link to={`/library/${hit.provenance.source_id}`}>{hit.provenance.source_title}</Link>
            {hit.provenance.locator_label ? (
              <span className="provenance__locator">{hit.provenance.locator_label}</span>
            ) : null}
            {hit.provenance.author ? <span>· {hit.provenance.author}</span> : null}
            {hit.provenance.published_on ? <span>· {hit.provenance.published_on}</span> : null}
          </>
        ) : (
          <span>{hit.subtitle}</span>
        )}
      </div>
    </article>
  )
}

export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const initialQuery = params.get('q') ?? ''
  const [query, setQuery] = useState(initialQuery)
  const [types, setTypes] = useState<TargetType[]>(
    (params.getAll('types').filter(Boolean) as TargetType[]) ?? [],
  )
  const [grouped, setGrouped] = useState(params.get('group') === '1')
  const debounced = useDebounced(query, 300)

  useEffect(() => {
    setQuery(initialQuery)
  }, [initialQuery])

  useEffect(() => {
    const next = new URLSearchParams()
    if (debounced) next.set('q', debounced)
    for (const type of types) next.append('types', type)
    if (grouped) next.set('group', '1')
    setParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, types.join(','), grouped])

  const results = useAsync(async () => {
    if (debounced.trim().length < 2) return null
    return api.search({ q: debounced, types, group: grouped, limit: 60 })
  }, [debounced, types.join(','), grouped])

  const status = useAsync(() => api.searchStatus(), [])
  const semantic = useAsync(async () => {
    if (debounced.trim().length < 2) return null
    return api.semanticSearch(debounced)
  }, [debounced])

  const totalLabel = useMemo(() => {
    if (!results.data) return ''
    return `${formatNumber(results.data.total)} match${results.data.total === 1 ? '' : 'es'}`
  }, [results.data])

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <h1>Search</h1>
          <p className="page__subtitle">
            Full-text search over sources, excerpts, knowledge objects, dossiers and entities — SQLite FTS5,
            entirely local. {results.data ? totalLabel : ''}
          </p>
        </div>
        <div className="page__actions">
          <Segmented
            label="Result layout"
            value={grouped ? 'grouped' : 'flat'}
            onChange={(value) => setGrouped(value === 'grouped')}
            options={[
              { value: 'flat', label: 'Flat' },
              { value: 'grouped', label: 'By source' },
            ]}
          />
        </div>
      </header>

      <div className="split">
        <div className="stack">
          <input
            className="input"
            style={{ fontSize: 'var(--text-md)', minHeight: 40 }}
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder='e.g. "gross margin" -crypto  ·  title:helios  ·  semis*'
            aria-label="Search query"
          />

          <div className="chip-row">
            {TYPES.map((type) => (
              <button
                key={type.value}
                type="button"
                className="chip"
                aria-pressed={types.includes(type.value)}
                onClick={() =>
                  setTypes((current) =>
                    current.includes(type.value)
                      ? current.filter((item) => item !== type.value)
                      : [...current, type.value],
                  )
                }
              >
                {type.label}
              </button>
            ))}
            {types.length > 0 ? (
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setTypes([])}>
                Clear type filter
              </button>
            ) : null}
          </div>

          {results.loading && debounced ? <Loading label="Searching" rows={4} /> : null}
          {results.error ? <ErrorState message={results.error} onRetry={results.reload} /> : null}

          {!debounced ? (
            <EmptyState
              icon="⌕"
              title="Search your knowledge base"
              body="Every match links back to the exact source and locator it came from."
            />
          ) : null}

          {results.data && results.data.total === 0 ? (
            <EmptyState
              icon="∅"
              title="No matches"
              body={`Nothing in the index matches “${debounced}”. Try fewer words, or a prefix search like ${debounced.split(' ')[0]}*`}
            />
          ) : null}

          {results.data && !grouped
            ? results.data.results.map((hit) => <HitRow key={`${hit.ref_type}-${hit.ref_id}`} hit={hit} />)
            : null}

          {results.data && grouped && results.data.groups
            ? results.data.groups.map((group) => (
                <section className="group" key={group.key}>
                  <header className="group__header">
                    {group.source_id ? (
                      <Link to={`/library/${group.source_id}`}>{group.source_title}</Link>
                    ) : (
                      <span>Other objects</span>
                    )}
                    {group.source_kind ? <Badge>{group.source_kind}</Badge> : null}
                    <span className="spacer" />
                    <span className="xs faint">{group.results.length} match(es)</span>
                  </header>
                  <div className="group__body">
                    {group.results.map((hit) => (
                      <HitRow key={`${hit.ref_type}-${hit.ref_id}`} hit={hit} />
                    ))}
                  </div>
                </section>
              ))
            : null}
        </div>

        <aside className="stack">
          <Section title="Query syntax">
            <ul className="list">
              {(status.data?.fulltext.syntax ?? []).map((item) => (
                <li key={item.example} className="list__item">
                  <div className="list__main">
                    <code className="list__title">{item.example}</code>
                    <span className="list__meta">{item.meaning}</span>
                  </div>
                </li>
              ))}
            </ul>
            {status.data ? (
              <p className="xs faint" style={{ marginTop: 8, marginBottom: 0 }}>
                {formatNumber(status.data.fulltext.indexed_objects)} objects indexed with{' '}
                {status.data.fulltext.engine}.
              </p>
            ) : null}
          </Section>

          <Section title="Semantic search">
            {semantic.data && semantic.data.enabled && semantic.data.available ? (
              <ul className="list">
                {semantic.data.results.length === 0 ? (
                  <li className="list__item">
                    <span className="small muted">No semantically similar objects above the noise floor.</span>
                  </li>
                ) : null}
                {semantic.data.results.map((item, index) => (
                  <li key={index} className="list__item">
                    <div className="list__main">
                      <span className="list__title">{String(item.label ?? '')}</span>
                      <span className="list__meta">
                        <Badge>{String(item.ref_type ?? '')}</Badge>
                        <span>similarity {Number(item.similarity ?? 0).toFixed(3)}</span>
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="small muted mt-0">
                {semantic.data?.detail ?? status.data?.semantic.detail ?? 'Semantic search is optional and disabled.'}{' '}
                <Link to="/settings">Configure it in Settings</Link> — full-text search is unaffected either way.
              </p>
            )}
          </Section>

          <Section title="Tips">
            <ul className="small muted" style={{ paddingLeft: 18, margin: 0 }}>
              <li>Excerpt hits carry a page, timestamp, section or row locator.</li>
              <li>Group by source when one document dominates the results.</li>
              <li>
                Filter the library instead when you want structured criteria — {titleCase('type, tag, entity, date')}.
              </li>
            </ul>
          </Section>
        </aside>
      </div>
    </div>
  )
}
