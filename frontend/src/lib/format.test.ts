import { describe, expect, it } from 'vitest'
import {
  confidenceLabel,
  formatBytes,
  formatDate,
  formatNumber,
  locatorLabel,
  parseTagInput,
  pluralize,
  relativeTime,
  stanceTone,
  statusTone,
  titleCase,
  truncate,
} from './format'

describe('formatBytes', () => {
  it('formats each magnitude', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB')
  })

  it('returns a dash for missing values', () => {
    expect(formatBytes(null)).toBe('—')
    expect(formatBytes(undefined)).toBe('—')
  })
})

describe('formatNumber', () => {
  it('groups thousands', () => {
    expect(formatNumber(1234567)).toBe('1,234,567')
  })
  it('handles missing values', () => {
    expect(formatNumber(null)).toBe('—')
    expect(formatNumber(Number.NaN)).toBe('—')
  })
})

describe('formatDate', () => {
  it('renders ISO dates unambiguously', () => {
    expect(formatDate('2026-07-24')).toBe('2026-07-24')
  })
  it('passes through unparseable values', () => {
    expect(formatDate('not-a-date')).toBe('not-a-date')
  })
})

describe('relativeTime', () => {
  const now = new Date('2026-08-03T12:00:00Z').getTime()

  it.each([
    ['2026-08-03T11:59:30Z', 'just now'],
    ['2026-08-03T11:30:00Z', '30m ago'],
    ['2026-08-03T06:00:00Z', '6h ago'],
    ['2026-08-01T12:00:00Z', '2d ago'],
  ])('%s -> %s', (value, expected) => {
    expect(relativeTime(value, now)).toBe(expected)
  })

  it('falls back to a date beyond a week', () => {
    expect(relativeTime('2026-06-01T12:00:00Z', now)).toBe('2026-06-01')
  })
})

describe('locatorLabel', () => {
  it.each([
    [{ page: 4 }, 'p. 4'],
    [{ timestamp: '12:30' }, '[12:30]'],
    [{ timestamp_seconds: 90 }, '[1:30]'],
    [{ row_start: 26, row_end: 50 }, 'rows 26-50'],
    [{ section: 'Risks' }, '§ Risks'],
    [{ pointer: '/positions' }, '/positions'],
    [{ index: 2 }, 'record 3'],
    [{}, ''],
  ])('%o', (locator, expected) => {
    expect(locatorLabel(locator)).toBe(expected)
  })

  it('mirrors the backend for null locators', () => {
    expect(locatorLabel(null)).toBe('')
  })
})

describe('tone helpers', () => {
  it('maps source and knowledge statuses', () => {
    expect(statusTone('ready')).toBe('success')
    expect(statusTone('needs_review')).toBe('warning')
    expect(statusTone('error')).toBe('danger')
    expect(statusTone('archived')).toBe('neutral')
  })

  it('maps claim stances', () => {
    expect(stanceTone('bull')).toBe('success')
    expect(stanceTone('bear')).toBe('danger')
    expect(stanceTone('risk')).toBe('warning')
    expect(stanceTone('question')).toBe('accent')
  })
})

describe('text helpers', () => {
  it('truncates on a word-safe boundary', () => {
    expect(truncate('one  two   three', 100)).toBe('one two three')
    expect(truncate('abcdefghij', 5)).toBe('abcd…')
  })

  it('parses and de-duplicates tag input', () => {
    expect(parseTagInput(' earnings, hlsx ,earnings,\nrisk ')).toEqual(['earnings', 'hlsx', 'risk'])
    expect(parseTagInput('')).toEqual([])
  })

  it('title-cases slugs', () => {
    expect(titleCase('needs_review')).toBe('Needs Review')
    expect(titleCase('web-article')).toBe('Web Article')
  })

  it('pluralises', () => {
    expect(pluralize(1, 'source')).toBe('1 source')
    expect(pluralize(3, 'source')).toBe('3 sources')
  })

  it('labels confidence bands', () => {
    expect(confidenceLabel(null)).toBe('unrated')
    expect(confidenceLabel(90)).toContain('high')
    expect(confidenceLabel(60)).toContain('moderate')
    expect(confidenceLabel(20)).toContain('low')
  })
})
