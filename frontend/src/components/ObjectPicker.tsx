import { useState } from 'react'
import { api } from '../lib/api'
import { useAsync, useDebounced } from '../lib/hooks'
import type { TargetType } from '../lib/types'
import { Modal } from './Modal'
import { EmptyState, ErrorState, Loading } from './ui'

export interface PickedObject {
  target_type: TargetType
  target_id: string
  label: string
  sublabel: string
}

const TYPE_LABELS: Record<string, string> = {
  source: 'Sources',
  excerpt: 'Excerpts',
  knowledge: 'Knowledge',
  entity: 'Entities',
  dossier: 'Dossiers',
}

/**
 * Search-driven picker used everywhere an object has to be chosen: dossier
 * items, links, comparison subjects, evidence.
 */
export function ObjectPicker({
  open,
  onClose,
  onPick,
  types = ['source', 'excerpt', 'knowledge', 'entity', 'dossier'],
  title = 'Choose an object',
  excludeIds = [],
}: {
  open: boolean
  onClose: () => void
  onPick: (picked: PickedObject) => void
  types?: TargetType[]
  title?: string
  excludeIds?: string[]
}) {
  const [query, setQuery] = useState('')
  const [activeType, setActiveType] = useState<TargetType | 'all'>('all')
  const debounced = useDebounced(query, 250)
  const searchTypes = activeType === 'all' ? types : [activeType]

  const state = useAsync(async () => {
    if (!open) return { results: [] as PickedObject[] }
    if (debounced.trim().length < 2) {
      // Without a query, show the most recent objects of the first allowed type.
      const type = searchTypes[0]
      if (type === 'source') {
        const page = await api.sources({ page_size: 20 })
        return {
          results: page.items.map((item) => ({
            target_type: 'source' as TargetType,
            target_id: item.id,
            label: item.title,
            sublabel: item.kind,
          })),
        }
      }
      if (type === 'knowledge') {
        const page = await api.knowledge({ limit: 20 })
        return {
          results: page.items.map((item) => ({
            target_type: 'knowledge' as TargetType,
            target_id: item.id,
            label: item.title,
            sublabel: `${item.kind} · ${item.status}`,
          })),
        }
      }
      if (type === 'entity') {
        const page = await api.entities({ limit: 30 })
        return {
          results: page.items.map((item) => ({
            target_type: 'entity' as TargetType,
            target_id: item.id,
            label: item.name,
            sublabel: item.kind,
          })),
        }
      }
      if (type === 'dossier') {
        const page = await api.dossiers()
        return {
          results: page.items.map((item) => ({
            target_type: 'dossier' as TargetType,
            target_id: item.id,
            label: item.title,
            sublabel: item.subject_kind,
          })),
        }
      }
      const page = await api.excerpts({ limit: 20 })
      return {
        results: page.items.map((item) => ({
          target_type: 'excerpt' as TargetType,
          target_id: item.id,
          label: item.text.slice(0, 110),
          sublabel: item.provenance && 'source_title' in item.provenance ? String(item.provenance.source_title) : 'excerpt',
        })),
      }
    }
    const response = await api.search({ q: debounced, types: searchTypes, limit: 30 })
    return {
      results: response.results.map((hit) => ({
        target_type: hit.ref_type,
        target_id: hit.ref_id,
        label: hit.title || hit.snippet.slice(0, 90),
        sublabel: hit.subtitle,
      })),
    }
  }, [open, debounced, activeType])

  const results = (state.data?.results ?? []).filter((item) => !excludeIds.includes(item.target_id))

  return (
    <Modal open={open} title={title} onClose={onClose}>
      <div className="stack">
        <input
          className="input"
          placeholder="Search by title or content…"
          value={query}
          autoFocus
          aria-label="Search objects"
          onChange={(event) => setQuery(event.target.value)}
        />
        {types.length > 1 ? (
          <div className="chip-row">
            <button type="button" className="chip" aria-pressed={activeType === 'all'} onClick={() => setActiveType('all')}>
              All
            </button>
            {types.map((type) => (
              <button
                key={type}
                type="button"
                className="chip"
                aria-pressed={activeType === type}
                onClick={() => setActiveType(type)}
              >
                {TYPE_LABELS[type] ?? type}
              </button>
            ))}
          </div>
        ) : null}

        {state.loading ? <Loading label="Searching" rows={3} /> : null}
        {state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : null}
        {!state.loading && !state.error && results.length === 0 ? (
          <EmptyState icon="⌕" title="Nothing found" body="Try a different term, or import the material first." />
        ) : null}

        <ul className="list">
          {results.map((item) => (
            <li key={`${item.target_type}:${item.target_id}`} className="list__item">
              <div className="list__main">
                <span className="list__title">{item.label}</span>
                <span className="list__meta">
                  <span className="badge">{item.target_type}</span>
                  {item.sublabel ? <span>{item.sublabel}</span> : null}
                </span>
              </div>
              <button
                type="button"
                className="btn btn--sm"
                onClick={() => {
                  onPick(item)
                  onClose()
                }}
              >
                Select
              </button>
            </li>
          ))}
        </ul>
      </div>
    </Modal>
  )
}
