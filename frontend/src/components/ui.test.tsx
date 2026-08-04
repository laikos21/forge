import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { HL_END, HL_START } from '../lib/highlight'
import type { Tag } from '../lib/types'
import { TagEditor } from './TagEditor'
import { Badge, EmptyState, ErrorState, GeneratedBadge, Highlighted, Loading, Provenance, Segmented } from './ui'

describe('Highlighted', () => {
  it('wraps matched terms in <mark> without parsing HTML', () => {
    const snippet = `Gross ${HL_START}margin${HL_END} expanded`
    const { container } = render(<Highlighted snippet={snippet} />)
    const marks = container.querySelectorAll('mark')
    expect(marks).toHaveLength(1)
    expect(marks[0].textContent).toBe('margin')
    expect(container.textContent).toBe('Gross margin expanded')
  })

  it('renders script-looking content as text', () => {
    const { container } = render(<Highlighted snippet={'<script>alert(1)</script>'} />)
    expect(container.querySelector('script')).toBeNull()
    expect(container.textContent).toContain('<script>alert(1)</script>')
  })
})

describe('state components', () => {
  it('renders an empty state with an action', () => {
    render(<EmptyState title="Nothing here" body="Import something" action={<button type="button">Import</button>} />)
    expect(screen.getByRole('status')).toHaveTextContent('Nothing here')
    expect(screen.getByRole('button', { name: 'Import' })).toBeInTheDocument()
  })

  it('renders an error state and calls the retry handler', async () => {
    const onRetry = vi.fn()
    render(<ErrorState message="Backend unreachable" onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Backend unreachable')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('announces loading state to assistive technology', () => {
    render(<Loading label="Loading library" />)
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true')
  })
})

describe('badges', () => {
  it('marks generated content visibly', () => {
    render(<GeneratedBadge by="ollama:llama3.1:8b" />)
    const badge = screen.getByTitle(/ollama:llama3.1:8b/)
    expect(badge).toHaveTextContent('generated')
  })

  it('applies the tone class', () => {
    const { container } = render(<Badge tone="danger">error</Badge>)
    expect(container.firstChild).toHaveClass('badge--danger')
  })
})

describe('Provenance', () => {
  it('shows the source, locator and author', () => {
    render(<Provenance sourceTitle="Q3 review" locator="p. 2" author="Desk" published="2026-07-24" />)
    expect(screen.getByText('Q3 review')).toBeInTheDocument()
    expect(screen.getByText('p. 2')).toBeInTheDocument()
    expect(screen.getByText('· Desk')).toBeInTheDocument()
  })
})

describe('Segmented', () => {
  it('reports the pressed option and switches', async () => {
    const onChange = vi.fn()
    render(
      <Segmented
        label="View"
        value="grid"
        onChange={onChange}
        options={[
          { value: 'grid', label: 'Grid' },
          { value: 'table', label: 'Table' },
        ]}
      />,
    )
    expect(screen.getByRole('button', { name: 'Grid' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Table' }))
    expect(onChange).toHaveBeenCalledWith('table')
  })
})

describe('TagEditor', () => {
  const tags: Tag[] = [
    { id: '1', slug: 'earnings', name: 'earnings', color: null },
    { id: '2', slug: 'hlsx', name: 'hlsx', color: null },
  ]

  it('lists existing tags', () => {
    render(<TagEditor tags={tags} onSave={vi.fn()} />)
    expect(screen.getByText('earnings')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit tags' })).toBeInTheDocument()
  })

  it('saves a parsed, de-duplicated list', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(<TagEditor tags={tags} onSave={onSave} />)
    await userEvent.click(screen.getByRole('button', { name: 'Edit tags' }))

    const input = screen.getByLabelText(/Tags \(comma separated\)/)
    await userEvent.clear(input)
    await userEvent.type(input, 'earnings, margins , earnings')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(onSave).toHaveBeenCalledWith(['earnings', 'margins'])
  })

  it('cancels without saving', async () => {
    const onSave = vi.fn()
    render(<TagEditor tags={tags} onSave={onSave} />)
    await userEvent.click(screen.getByRole('button', { name: 'Edit tags' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Edit tags' })).toBeInTheDocument()
  })

  it('offers to add tags when there are none', () => {
    render(<TagEditor tags={[]} onSave={vi.fn()} />)
    expect(screen.getByText('No tags')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add tags' })).toBeInTheDocument()
  })
})
