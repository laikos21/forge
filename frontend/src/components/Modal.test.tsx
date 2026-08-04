import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Modal } from './Modal'

describe('Modal', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <Modal open={false} title="Hidden" onClose={vi.fn()}>
        body
      </Modal>,
    )
    expect(container.firstChild).toBeNull()
  })

  it('exposes a labelled dialog and focuses inside it', () => {
    render(
      <Modal open title="New dossier" onClose={vi.fn()}>
        <input aria-label="Title" />
      </Modal>,
    )
    const dialog = screen.getByRole('dialog', { name: 'New dossier' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByLabelText('Title')).toHaveFocus()
  })

  it('closes on Escape', async () => {
    const onClose = vi.fn()
    render(
      <Modal open title="Closable" onClose={onClose}>
        <input aria-label="Field" />
      </Modal>,
    )
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })

  it('closes from the header button', async () => {
    const onClose = vi.fn()
    render(
      <Modal open title="Closable" onClose={onClose}>
        body
      </Modal>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Close dialog' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
