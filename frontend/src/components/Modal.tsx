import type { ReactNode } from 'react'
import { useDialog } from '../lib/hooks'

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  wide = false,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  const ref = useDialog(open, onClose)
  if (!open) return null

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        className={wide ? 'modal modal--wide' : 'modal'}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={ref}
      >
        <header className="modal__header">
          <h2 style={{ fontSize: 'var(--text-md)' }}>{title}</h2>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onClose} aria-label="Close dialog">
            ✕
          </button>
        </header>
        <div className="modal__body">{children}</div>
        {footer ? <footer className="modal__footer">{footer}</footer> : null}
      </div>
    </div>
  )
}

export function ConfirmButton({
  label,
  confirmLabel = 'Confirm',
  message,
  onConfirm,
  className = 'btn btn--danger btn--sm',
}: {
  label: string
  confirmLabel?: string
  message: string
  onConfirm: () => void
  className?: string
}) {
  return (
    <button
      type="button"
      className={className}
      onClick={() => {
        if (window.confirm(message)) onConfirm()
      }}
      title={message}
    >
      {label}
      <span className="sr-only" style={{ position: 'absolute', left: -9999 }}>
        {confirmLabel}
      </span>
    </button>
  )
}
