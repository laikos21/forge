import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Markdown, parseBlocks } from './markdown'

describe('parseBlocks', () => {
  it('recognises headings, lists and quotes', () => {
    const blocks = parseBlocks('# Title\n\n- one\n- two\n\n> quoted\n\nplain paragraph')
    expect(blocks.map((block) => block.type)).toEqual(['heading', 'ul', 'quote', 'paragraph'])
    expect(blocks[0].level).toBe(1)
    expect(blocks[1].lines).toEqual(['one', 'two'])
  })

  it('groups ordered list items', () => {
    const blocks = parseBlocks('1. first\n2. second')
    expect(blocks).toHaveLength(1)
    expect(blocks[0].type).toBe('ol')
  })

  it('treats a rule as its own block', () => {
    expect(parseBlocks('a\n\n---\n\nb').map((block) => block.type)).toEqual(['paragraph', 'rule', 'paragraph'])
  })

  it('returns nothing for empty input', () => {
    expect(parseBlocks('')).toEqual([])
  })
})

describe('Markdown', () => {
  it('renders headings and emphasis as elements', () => {
    render(<Markdown text={'## Bull case\n\nMargin is **mix-driven** and _reversible_.'} />)
    expect(screen.getByRole('heading', { name: 'Bull case' })).toBeInTheDocument()
    expect(screen.getByText('mix-driven').tagName).toBe('STRONG')
    expect(screen.getByText('reversible').tagName).toBe('EM')
  })

  it('renders list items', () => {
    render(<Markdown text={'- alpha\n- beta'} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('never injects raw HTML', () => {
    const { container } = render(<Markdown text={'<img src=x onerror="alert(1)">  plain'} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toContain('<img src=x onerror="alert(1)">')
  })

  it('links bare URLs safely', () => {
    render(<Markdown text="see https://example.invalid/doc" />)
    const link = screen.getByRole('link', { name: 'https://example.invalid/doc' })
    expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'))
  })

  it('renders nothing for empty text', () => {
    const { container } = render(<Markdown text="" />)
    expect(container.firstChild).toBeNull()
  })
})
