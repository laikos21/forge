import { describe, expect, it } from 'vitest'
import { highlightTerms, HL_END, HL_START, queryTerms, splitHighlights } from './highlight'

const wrap = (text: string) => `${HL_START}${text}${HL_END}`

describe('splitHighlights', () => {
  it('splits a snippet into marked and unmarked segments', () => {
    const snippet = `Gross ${wrap('margin')} expanded ${wrap('240')} basis points`
    expect(splitHighlights(snippet)).toEqual([
      { text: 'Gross ', marked: false },
      { text: 'margin', marked: true },
      { text: ' expanded ', marked: false },
      { text: '240', marked: true },
      { text: ' basis points', marked: false },
    ])
  })

  it('handles a snippet with no markers', () => {
    expect(splitHighlights('plain text')).toEqual([{ text: 'plain text', marked: false }])
  })

  it('returns nothing for an empty snippet', () => {
    expect(splitHighlights('')).toEqual([])
  })

  it('does not lose text when a marker is unbalanced', () => {
    const segments = splitHighlights(`start ${HL_START}unclosed`)
    expect(segments.map((segment) => segment.text).join('')).toBe('start unclosed')
    expect(segments.every((segment) => !segment.marked)).toBe(true)
  })

  it('keeps the marked text out of the surrounding segments', () => {
    const segments = splitHighlights(wrap('only'))
    expect(segments).toEqual([{ text: 'only', marked: true }])
  })
})

describe('highlightTerms', () => {
  it('marks every case-insensitive occurrence', () => {
    const segments = highlightTerms('Margin and margin again', ['margin'])
    expect(segments.filter((segment) => segment.marked).map((segment) => segment.text)).toEqual([
      'Margin',
      'margin',
    ])
  })

  it('ignores one-character terms', () => {
    expect(highlightTerms('abc', ['a'])).toEqual([{ text: 'abc', marked: false }])
  })

  it('escapes regex metacharacters in terms', () => {
    const segments = highlightTerms('a+b and c', ['a+b'])
    expect(segments.some((segment) => segment.marked && segment.text === 'a+b')).toBe(true)
  })
})

describe('queryTerms', () => {
  it('keeps positive terms and phrases', () => {
    expect(queryTerms('"gross margin" inventory')).toEqual(['gross margin', 'inventory'])
  })

  it('drops negated terms', () => {
    expect(queryTerms('margin -crypto')).toEqual(['margin'])
  })

  it('strips column prefixes and trailing wildcards', () => {
    expect(queryTerms('title:helios semis*')).toEqual(['helios', 'semis'])
  })
})
