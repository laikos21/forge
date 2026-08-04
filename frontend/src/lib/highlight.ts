/**
 * Search snippets arrive with matched terms wrapped in two control characters
 * (U+001F / U+001E). Splitting on them yields plain-text segments that React
 * renders as <mark>, so highlighting never requires `dangerouslySetInnerHTML`.
 */

export const HL_START = '\u001f'
export const HL_END = '\u001e'

export interface Segment {
  text: string
  marked: boolean
}

export function splitHighlights(snippet: string, start = HL_START, end = HL_END): Segment[] {
  if (!snippet) return []
  const segments: Segment[] = []
  let cursor = 0

  while (cursor < snippet.length) {
    const openIndex = snippet.indexOf(start, cursor)
    if (openIndex === -1) {
      segments.push({ text: snippet.slice(cursor), marked: false })
      break
    }
    if (openIndex > cursor) {
      segments.push({ text: snippet.slice(cursor, openIndex), marked: false })
    }
    const closeIndex = snippet.indexOf(end, openIndex + start.length)
    if (closeIndex === -1) {
      // Unbalanced marker: treat the remainder as plain text rather than losing it.
      segments.push({ text: snippet.slice(openIndex + start.length), marked: false })
      break
    }
    segments.push({ text: snippet.slice(openIndex + start.length, closeIndex), marked: true })
    cursor = closeIndex + end.length
  }

  return segments.filter((segment) => segment.text.length > 0)
}

/** Highlight plain text locally (used by the reader, which has no FTS snippet). */
export function highlightTerms(text: string, terms: string[]): Segment[] {
  const cleaned = terms.map((term) => term.trim()).filter((term) => term.length > 1)
  if (cleaned.length === 0 || !text) return [{ text, marked: false }]

  const escaped = cleaned.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const pattern = new RegExp(`(${escaped.join('|')})`, 'gi')
  const segments: Segment[] = []
  let lastIndex = 0

  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > lastIndex) segments.push({ text: text.slice(lastIndex, index), marked: false })
    segments.push({ text: match[0], marked: true })
    lastIndex = index + match[0].length
  }
  if (lastIndex < text.length) segments.push({ text: text.slice(lastIndex), marked: false })
  return segments
}

/** Extract the searchable terms from a FORGE query string. */
export function queryTerms(query: string): string[] {
  const terms: string[] = []
  const pattern = /(-?)(?:"([^"]*)"|(\S+))/g
  for (const match of query.matchAll(pattern)) {
    if (match[1] === '-') continue
    const value = (match[2] ?? match[3] ?? '').replace(/^(title|body):/i, '').replace(/\*$/, '')
    if (value.length > 1) terms.push(value)
  }
  return terms
}
