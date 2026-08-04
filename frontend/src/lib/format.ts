/** Presentation helpers. Pure functions - unit-tested, never touching the DOM. */

import type { KnowledgeKind, Locator, SourceKind, SourceStatus } from './types'

export const SOURCE_KIND_LABELS: Record<SourceKind, string> = {
  pdf: 'PDF',
  text: 'Text',
  markdown: 'Markdown',
  csv: 'CSV',
  json: 'JSON',
  transcript: 'Transcript',
  image: 'Image',
  note: 'Note',
  web_article: 'Web article',
}

export const SOURCE_KIND_ICONS: Record<SourceKind, string> = {
  pdf: '▤',
  text: '≡',
  markdown: '#',
  csv: '⊞',
  json: '{}',
  transcript: '⏱',
  image: '▣',
  note: '✎',
  web_article: '⌘',
}

export const KNOWLEDGE_KIND_LABELS: Record<KnowledgeKind, string> = {
  insight: 'Insight',
  rule: 'Rule',
  hypothesis: 'Hypothesis',
  decision: 'Decision',
  quote: 'Quote',
  note: 'Note',
}

export const KNOWLEDGE_KIND_ICONS: Record<KnowledgeKind, string> = {
  insight: '✦',
  rule: '⚖',
  hypothesis: '?',
  decision: '⌥',
  quote: '❝',
  note: '✎',
}

export type BadgeTone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'generated'

export function statusTone(status: SourceStatus | string): BadgeTone {
  switch (status) {
    case 'ready':
    case 'active':
    case 'supported':
    case 'made':
    case 'executed':
      return 'success'
    case 'needs_review':
    case 'processing':
    case 'under_review':
    case 'proposed':
    case 'open':
    case 'watching':
      return 'warning'
    case 'error':
    case 'refuted':
    case 'reversed':
      return 'danger'
    case 'archived':
    case 'retired':
    case 'inconclusive':
      return 'neutral'
    default:
      return 'neutral'
  }
}

export function stanceTone(stance: string): BadgeTone {
  switch (stance) {
    case 'bull':
    case 'supports':
      return 'success'
    case 'bear':
    case 'refutes':
      return 'danger'
    case 'risk':
      return 'warning'
    case 'question':
      return 'accent'
    default:
      return 'neutral'
  }
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  // One decimal below 100, none above: "2.0 KB", "512 KB", "1.4 GB".
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[unit]}`
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString('en-US')
}

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  // A calendar date has no timezone. Passing it through `new Date` would parse
  // it as UTC midnight and render the previous day west of Greenwich, so
  // date-only values are returned verbatim - already ISO, already unambiguous.
  if (DATE_ONLY.test(value)) return value
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleDateString('en-CA')
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return `${date.toLocaleDateString('en-CA')} ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
}

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

export function relativeTime(value: string | null | undefined, now: number = Date.now()): string {
  if (!value) return '—'
  const time = new Date(value).getTime()
  if (Number.isNaN(time)) return String(value)
  const delta = now - time
  if (delta < MINUTE) return 'just now'
  if (delta < HOUR) return `${Math.floor(delta / MINUTE)}m ago`
  if (delta < DAY) return `${Math.floor(delta / HOUR)}h ago`
  if (delta < 7 * DAY) return `${Math.floor(delta / DAY)}d ago`
  return formatDate(value)
}

/** Human label for a locator, mirroring the backend's `locator_label`. */
export function locatorLabel(locator: Locator | null | undefined): string {
  if (!locator) return ''
  if (locator.page !== undefined) return `p. ${locator.page}`
  if (locator.timestamp) return `[${locator.timestamp}]`
  if (locator.timestamp_seconds !== undefined) {
    const seconds = Number(locator.timestamp_seconds)
    const minutes = Math.floor(seconds / 60)
    return `[${minutes}:${String(seconds % 60).padStart(2, '0')}]`
  }
  if (locator.row_start !== undefined) return `rows ${locator.row_start}-${locator.row_end ?? locator.row_start}`
  if (locator.section) return `§ ${locator.section}`
  if (locator.pointer) return String(locator.pointer)
  if (locator.index !== undefined) return `record ${Number(locator.index) + 1}`
  return ''
}

export function truncate(text: string, limit = 160): string {
  const collapsed = text.replace(/\s+/g, ' ').trim()
  return collapsed.length <= limit ? collapsed : `${collapsed.slice(0, limit - 1).trimEnd()}…`
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${formatNumber(count)} ${count === 1 ? singular : plural}`
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
    .trim()
}

/** Parse a comma/space separated tag input into a clean, de-duplicated list. */
export function parseTagInput(raw: string): string[] {
  return Array.from(
    new Set(
      raw
        .split(/[,\n]/)
        .map((tag) => tag.trim())
        .filter(Boolean),
    ),
  )
}

export function confidenceLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'unrated'
  if (value >= 80) return `${value}% · high`
  if (value >= 50) return `${value}% · moderate`
  return `${value}% · low`
}
