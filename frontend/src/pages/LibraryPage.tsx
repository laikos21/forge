import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useToast } from '../components/Toasts'
import { Badge, DemoBadge, EmptyState, ErrorState, Loading, Segmented } from '../components/ui'
import { api, downloadBlob } from '../lib/api'
import type { LibraryFilters } from '../lib/api'
import {
  countActiveFilters,
  DEFAULT_FILTERS,
  filtersToSearch,
  parseFilters,
  SORT_OPTIONS,
  toggleValue,
} from '../lib/filters'
import {
  formatBytes,
  formatDate,
  formatNumber,
  relativeTime,
  SOURCE_KIND_ICONS,
  SOURCE_KIND_LABELS,
  statusTone,
  titleCase,
  truncate,
} from '../lib/format'
import { useAsync, useStoredState } from '../lib/hooks'
import type { SourceKind } from '../lib/types'

export function LibraryPage() {
  const [params, setParams] = useSearchParams()
  const toast = useToast()
  const filters = useMemo(() => parseFilters(params), [params])
  const [view, setView] = useStoredState<'grid' | 'table'>('forge.library.view', 'grid')
  const [selection, setSelection] = useState<string[]>([])

  const sources = useAsync(() => api.sources(filters), [params.toString()])
  const tags = useAsync(() => api.tags(), [])
  const entities = useAsync(() => api.entities({ limit: 300 }), [])

  const update = (patch: Partial<LibraryFilters>) => {
    const next = { ...filters, ...patch, page: patch.page ?? 1 }
    setParams(filtersToSearch(next))
  }

  const activeCount = countActiveFilters(filters)
  const facets = sources.data?.facets ?? {}
  const items = sources.data?.items ?? []

  const exportSelection = async () => {
    if (selection.length === 0) return
    try {
      const blob = await api.exportSources(selection, true)
      downloadBlob(blob, `forge-sources-${new Date().toISOString().slice(0, 10)}.zip`)
      toast.success(`Exported ${selection.length} source(s).`)
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const toggleSelection = (id: string) =>
    setSelection((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]))

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <h1>Library</h1>
          <p className="page__subtitle">
            {sources.data
              ? `${formatNumber(sources.data.total)} sources${activeCount ? ` matching ${activeCount} filter(s)` : ''}`
              : 'Everything you have imported, with its original file and normalized text.'}
          </p>
        </div>
        <div className="page__actions">
          <Segmented
            label="View mode"
            value={view}
            onChange={setView}
            options={[
              { value: 'grid', label: 'Grid' },
              { value: 'table', label: 'Table' },
            ]}
          />
          <select
            className="select"
            style={{ width: 'auto' }}
            aria-label="Sort order"
            value={filters.sort}
            onChange={(event) => update({ sort: event.target.value })}
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {selection.length > 0 ? (
            <button type="button" className="btn btn--primary" onClick={() => void exportSelection()}>
              Export {selection.length} selected
            </button>
          ) : null}
          <Link className="btn" to="/inbox">
            Import
          </Link>
        </div>
      </header>

      <div className="split">
        <div className="stack">
          <div className="row">
            <input
              className="input"
              style={{ maxWidth: 340 }}
              placeholder="Filter by title, author or summary…"
              aria-label="Filter sources"
              value={filters.q ?? ''}
              onChange={(event) => update({ q: event.target.value })}
            />
            {activeCount > 0 ? (
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setParams(filtersToSearch(DEFAULT_FILTERS))}>
                Clear filters ({activeCount})
              </button>
            ) : null}
          </div>

          {sources.loading && !sources.data ? <Loading label="Loading library" rows={5} /> : null}
          {sources.error ? <ErrorState message={sources.error} onRetry={sources.reload} /> : null}

          {!sources.loading && items.length === 0 ? (
            <EmptyState
              icon="▤"
              title={activeCount ? 'No sources match these filters' : 'The library is empty'}
              body={
                activeCount
                  ? 'Loosen a filter, or clear them all to see everything.'
                  : 'Import a PDF, a transcript or a note from the Inbox to start building the library.'
              }
              action={
                activeCount ? (
                  <button type="button" className="btn" onClick={() => setParams(filtersToSearch(DEFAULT_FILTERS))}>
                    Clear filters
                  </button>
                ) : (
                  <Link className="btn btn--primary" to="/inbox">
                    Go to the Inbox
                  </Link>
                )
              }
            />
          ) : null}

          {items.length > 0 && view === 'grid' ? (
            <div className="grid grid--cards">
              {items.map((source) => (
                <div key={source.id} style={{ position: 'relative' }}>
                  <Link className="source-card" to={`/library/${source.id}`}>
                    <div className="row" style={{ gap: 8 }}>
                      <span aria-hidden="true" className="faint">
                        {SOURCE_KIND_ICONS[source.kind as SourceKind] ?? '≡'}
                      </span>
                      <Badge>{SOURCE_KIND_LABELS[source.kind as SourceKind] ?? source.kind}</Badge>
                      {source.status !== 'ready' ? (
                        <Badge tone={statusTone(source.status)}>{titleCase(source.status)}</Badge>
                      ) : null}
                      {source.is_demo ? <DemoBadge /> : null}
                    </div>
                    <div className="source-card__title">{source.title}</div>
                    {source.summary ? <p className="source-card__summary">{truncate(source.summary, 180)}</p> : null}
                    <div className="source-card__foot">
                      <span>{source.author ?? 'Unattributed'}</span>
                      <span>
                        {formatNumber(source.word_count)} words · {relativeTime(source.imported_at)}
                      </span>
                    </div>
                    {source.tags.length > 0 ? (
                      <div className="tag-list">
                        {source.tags.slice(0, 4).map((tag) => (
                          <span key={tag.id} className="tag">
                            {tag.name}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </Link>
                  <label
                    className="checkbox"
                    style={{ position: 'absolute', top: 12, right: 12 }}
                    title="Select for export"
                  >
                    <input
                      type="checkbox"
                      checked={selection.includes(source.id)}
                      onChange={() => toggleSelection(source.id)}
                      aria-label={`Select ${source.title}`}
                    />
                  </label>
                </div>
              ))}
            </div>
          ) : null}

          {items.length > 0 && view === 'table' ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th style={{ width: 34 }}>
                      <input
                        type="checkbox"
                        aria-label="Select all on this page"
                        checked={items.every((item) => selection.includes(item.id))}
                        onChange={(event) =>
                          setSelection(event.target.checked ? items.map((item) => item.id) : [])
                        }
                      />
                    </th>
                    <th>Title</th>
                    <th>Type</th>
                    <th>Author</th>
                    <th>Published</th>
                    <th className="table__num">Words</th>
                    <th className="table__num">Excerpts</th>
                    <th>Imported</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((source) => (
                    <tr key={source.id}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selection.includes(source.id)}
                          onChange={() => toggleSelection(source.id)}
                          aria-label={`Select ${source.title}`}
                        />
                      </td>
                      <td>
                        <Link to={`/library/${source.id}`}>{source.title}</Link>
                        {source.is_demo ? <> <DemoBadge /></> : null}
                      </td>
                      <td>{SOURCE_KIND_LABELS[source.kind as SourceKind] ?? source.kind}</td>
                      <td className="muted">{source.author ?? '—'}</td>
                      <td className="muted nowrap">{formatDate(source.published_on)}</td>
                      <td className="table__num">{formatNumber(source.word_count)}</td>
                      <td className="table__num">{source.excerpt_count}</td>
                      <td className="muted nowrap">{relativeTime(source.imported_at)}</td>
                      <td>
                        <Badge tone={statusTone(source.status)}>{titleCase(source.status)}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {sources.data && (sources.data.pages ?? 1) > 1 ? (
            <div className="row row--between">
              <span className="small muted">
                Page {sources.data.page} of {sources.data.pages}
              </span>
              <div className="btn-group">
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={(filters.page ?? 1) <= 1}
                  onClick={() => update({ page: (filters.page ?? 1) - 1 })}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={(sources.data.page ?? 1) >= (sources.data.pages ?? 1)}
                  onClick={() => update({ page: (filters.page ?? 1) + 1 })}
                >
                  Next
                </button>
              </div>
            </div>
          ) : null}
        </div>

        <aside className="card filters" aria-label="Filters">
          <div>
            <div className="filters__title">Type</div>
            <div className="chip-row">
              {Object.entries(facets.kind ?? {}).map(([kind, count]) => (
                <button
                  key={kind}
                  type="button"
                  className="chip"
                  aria-pressed={filters.kind?.includes(kind) ?? false}
                  onClick={() => update({ kind: toggleValue(filters.kind, kind) })}
                >
                  {SOURCE_KIND_LABELS[kind as SourceKind] ?? kind} <span className="faint">{count}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="filters__group">
            <div className="filters__title">Status</div>
            <div className="chip-row">
              {Object.entries(facets.status ?? {}).map(([status, count]) => (
                <button
                  key={status}
                  type="button"
                  className="chip"
                  aria-pressed={filters.status?.includes(status) ?? false}
                  onClick={() => update({ status: toggleValue(filters.status, status) })}
                >
                  {titleCase(status)} <span className="faint">{count}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="filters__group">
            <div className="filters__title">Tags</div>
            <div className="chip-row">
              {(tags.data?.items ?? []).slice(0, 24).map((tag) => (
                <button
                  key={tag.id}
                  type="button"
                  className="chip"
                  aria-pressed={filters.tag?.includes(tag.slug) ?? false}
                  onClick={() => update({ tag: toggleValue(filters.tag, tag.slug) })}
                >
                  {tag.name} <span className="faint">{tag.usage_count ?? 0}</span>
                </button>
              ))}
              {(tags.data?.items.length ?? 0) === 0 ? <span className="xs faint">No tags yet.</span> : null}
            </div>
          </div>

          <div className="filters__group">
            <div className="filters__title">Entity (ticker, company, person, topic, theme)</div>
            <select
              className="select"
              aria-label="Filter by entity"
              value={filters.entity_id?.[0] ?? ''}
              onChange={(event) => update({ entity_id: event.target.value ? [event.target.value] : [] })}
            >
              <option value="">Any entity</option>
              {(entities.data?.items ?? []).map((entity) => (
                <option key={entity.id} value={entity.id}>
                  {entity.kind}: {entity.name} ({entity.source_count})
                </option>
              ))}
            </select>
          </div>

          <div className="filters__group">
            <div className="filters__title">Author</div>
            <input
              className="input"
              aria-label="Filter by author"
              value={filters.author ?? ''}
              onChange={(event) => update({ author: event.target.value })}
              placeholder="Any author"
            />
          </div>

          <div className="filters__group">
            <div className="filters__title">Date range</div>
            <select
              className="select"
              aria-label="Date field"
              value={filters.date_field ?? 'imported'}
              onChange={(event) => update({ date_field: event.target.value })}
            >
              <option value="imported">Imported date</option>
              <option value="published">Publication date</option>
            </select>
            <div className="row" style={{ marginTop: 8, gap: 8 }}>
              <input
                className="input"
                type="date"
                aria-label="From date"
                value={filters.date_from ?? ''}
                onChange={(event) => update({ date_from: event.target.value })}
              />
              <input
                className="input"
                type="date"
                aria-label="To date"
                value={filters.date_to ?? ''}
                onChange={(event) => update({ date_to: event.target.value })}
              />
            </div>
          </div>

          {sources.data ? (
            <div className="filters__group xs faint">
              Storage: {formatNumber(sources.data.total)} sources ·{' '}
              {formatBytes(items.reduce((total, item) => total + (item.byte_size ?? 0), 0))} on this page
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  )
}
