/**
 * Library filter state <-> URL query string.
 *
 * The URL is the single source of truth for the library view, so a filtered
 * list can be bookmarked, shared between windows and restored by the back
 * button. These are pure functions, tested independently of React.
 */

import type { LibraryFilters } from './api'

export const SORT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'imported_desc', label: 'Newest import' },
  { value: 'imported_asc', label: 'Oldest import' },
  { value: 'updated_desc', label: 'Recently updated' },
  { value: 'published_desc', label: 'Publication date' },
  { value: 'title_asc', label: 'Title A→Z' },
  { value: 'title_desc', label: 'Title Z→A' },
  { value: 'words_desc', label: 'Longest' },
]

export const DEFAULT_FILTERS: LibraryFilters = {
  q: '',
  kind: [],
  status: [],
  tag: [],
  entity_id: [],
  author: '',
  date_field: 'imported',
  date_from: '',
  date_to: '',
  sort: 'imported_desc',
  page: 1,
  page_size: 24,
}

const ARRAY_KEYS = ['kind', 'status', 'tag', 'entity_id'] as const
const SCALAR_KEYS = ['q', 'author', 'language', 'date_field', 'date_from', 'date_to', 'sort'] as const

export function parseFilters(search: URLSearchParams): LibraryFilters {
  const filters: LibraryFilters = { ...DEFAULT_FILTERS, kind: [], status: [], tag: [], entity_id: [] }
  for (const key of ARRAY_KEYS) {
    const values = search.getAll(key).filter(Boolean)
    if (values.length) filters[key] = values
  }
  for (const key of SCALAR_KEYS) {
    const value = search.get(key)
    if (value) filters[key] = value
  }
  const page = Number(search.get('page'))
  if (Number.isFinite(page) && page > 0) filters.page = page
  const pageSize = Number(search.get('page_size'))
  if (Number.isFinite(pageSize) && pageSize > 0) filters.page_size = pageSize
  return filters
}

export function filtersToSearch(filters: LibraryFilters): URLSearchParams {
  const search = new URLSearchParams()
  for (const key of ARRAY_KEYS) {
    for (const value of filters[key] ?? []) search.append(key, value)
  }
  for (const key of SCALAR_KEYS) {
    const value = filters[key]
    if (value && value !== DEFAULT_FILTERS[key]) search.set(key, String(value))
  }
  if (filters.page && filters.page > 1) search.set('page', String(filters.page))
  if (filters.page_size && filters.page_size !== DEFAULT_FILTERS.page_size) {
    search.set('page_size', String(filters.page_size))
  }
  return search
}

export function toggleValue(values: string[] | undefined, value: string): string[] {
  const current = values ?? []
  return current.includes(value) ? current.filter((item) => item !== value) : [...current, value]
}

export function countActiveFilters(filters: LibraryFilters): number {
  let count = 0
  for (const key of ARRAY_KEYS) count += (filters[key] ?? []).length
  for (const key of SCALAR_KEYS) {
    if (key === 'sort' || key === 'date_field') continue
    if (filters[key]) count += 1
  }
  return count
}

export function describeFilters(filters: LibraryFilters): string[] {
  const parts: string[] = []
  if (filters.q) parts.push(`text “${filters.q}”`)
  if (filters.kind?.length) parts.push(`type: ${filters.kind.join(', ')}`)
  if (filters.status?.length) parts.push(`status: ${filters.status.join(', ')}`)
  if (filters.tag?.length) parts.push(`tag: ${filters.tag.join(', ')}`)
  if (filters.entity_id?.length) parts.push(`${filters.entity_id.length} entity filter(s)`)
  if (filters.author) parts.push(`author: ${filters.author}`)
  if (filters.date_from || filters.date_to) {
    parts.push(`${filters.date_field === 'published' ? 'published' : 'imported'} ${filters.date_from || '…'} → ${filters.date_to || '…'}`)
  }
  return parts
}
