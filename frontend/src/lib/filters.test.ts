import { describe, expect, it } from 'vitest'
import {
  countActiveFilters,
  DEFAULT_FILTERS,
  describeFilters,
  filtersToSearch,
  parseFilters,
  toggleValue,
} from './filters'

describe('parseFilters', () => {
  it('reads repeated array parameters', () => {
    const filters = parseFilters(new URLSearchParams('kind=pdf&kind=csv&tag=hlsx'))
    expect(filters.kind).toEqual(['pdf', 'csv'])
    expect(filters.tag).toEqual(['hlsx'])
  })

  it('falls back to defaults', () => {
    const filters = parseFilters(new URLSearchParams(''))
    expect(filters.sort).toBe(DEFAULT_FILTERS.sort)
    expect(filters.page).toBe(1)
    expect(filters.kind).toEqual([])
  })

  it('ignores an invalid page', () => {
    expect(parseFilters(new URLSearchParams('page=-3')).page).toBe(1)
  })
})

describe('filtersToSearch', () => {
  it('round-trips through the URL', () => {
    const filters = {
      ...DEFAULT_FILTERS,
      kind: ['pdf'],
      tag: ['hlsx', 'earnings'],
      q: 'margin',
      page: 2,
    }
    const parsed = parseFilters(filtersToSearch(filters))
    expect(parsed.kind).toEqual(['pdf'])
    expect(parsed.tag).toEqual(['hlsx', 'earnings'])
    expect(parsed.q).toBe('margin')
    expect(parsed.page).toBe(2)
  })

  it('omits default values to keep URLs short', () => {
    expect(filtersToSearch(DEFAULT_FILTERS).toString()).toBe('')
  })
})

describe('toggleValue', () => {
  it('adds and removes', () => {
    expect(toggleValue(['a'], 'b')).toEqual(['a', 'b'])
    expect(toggleValue(['a', 'b'], 'a')).toEqual(['b'])
    expect(toggleValue(undefined, 'a')).toEqual(['a'])
  })
})

describe('countActiveFilters', () => {
  it('counts array entries and non-default scalars', () => {
    expect(countActiveFilters(DEFAULT_FILTERS)).toBe(0)
    expect(countActiveFilters({ ...DEFAULT_FILTERS, kind: ['pdf', 'csv'], q: 'x' })).toBe(3)
  })

  it('does not count sort or date field', () => {
    expect(countActiveFilters({ ...DEFAULT_FILTERS, sort: 'title_asc', date_field: 'published' })).toBe(0)
  })
})

describe('describeFilters', () => {
  it('produces readable descriptions', () => {
    const parts = describeFilters({ ...DEFAULT_FILTERS, q: 'margin', kind: ['pdf'], author: 'Desk' })
    expect(parts.join(' | ')).toContain('text “margin”')
    expect(parts.join(' | ')).toContain('type: pdf')
    expect(parts.join(' | ')).toContain('author: Desk')
  })
})
