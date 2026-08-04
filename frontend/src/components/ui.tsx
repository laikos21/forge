/** Presentational primitives. No data fetching, no business rules. */

import type { ReactNode } from 'react'
import type { BadgeTone } from '../lib/format'
import { splitHighlights } from '../lib/highlight'
import type { Segment } from '../lib/highlight'

export function Badge({
  children,
  tone = 'neutral',
  title,
}: {
  children: ReactNode
  tone?: BadgeTone
  title?: string
}) {
  return (
    <span className={tone === 'neutral' ? 'badge' : `badge badge--${tone}`} title={title}>
      {children}
    </span>
  )
}

export function GeneratedBadge({ by }: { by?: string | null }) {
  return (
    <Badge tone="generated" title={by ? `Generated with ${by}. Review before relying on it.` : 'Model-generated'}>
      ⚙ generated
    </Badge>
  )
}

export function DemoBadge() {
  return (
    <span className="badge badge--demo" title="Demonstration content shipped with FORGE">
      demo
    </span>
  )
}

export function EmptyState({
  icon = '◇',
  title,
  body,
  action,
}: {
  icon?: string
  title: string
  body?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="empty" role="status">
      <div className="empty__icon" aria-hidden="true">
        {icon}
      </div>
      <div className="empty__title">{title}</div>
      {body ? <div className="empty__body">{body}</div> : null}
      {action}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-state" role="alert">
      <span aria-hidden="true">⚠</span>
      <div className="stack stack--tight">
        <strong>Something went wrong</strong>
        <span className="small">{message}</span>
        {onRetry ? (
          <div>
            <button type="button" className="btn btn--sm" onClick={onRetry}>
              Try again
            </button>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function Loading({ label = 'Loading', rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="stack stack--tight" role="status" aria-live="polite" aria-busy="true">
      <span className="xs faint">{label}…</span>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton" style={{ width: `${100 - index * 12}%`, height: index === 0 ? 18 : 14 }} />
      ))}
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="row" style={{ gap: 8 }}>
      <span className="spinner" aria-hidden="true" />
      {label ? <span className="xs faint">{label}</span> : null}
      <span className="sr-only" style={{ position: 'absolute', left: -9999 }}>
        Loading
      </span>
    </span>
  )
}

export function Section({
  title,
  action,
  children,
  description,
  id,
}: {
  title: string
  action?: ReactNode
  children: ReactNode
  description?: ReactNode
  id?: string
}) {
  return (
    <section className="card" id={id} aria-labelledby={id ? `${id}-title` : undefined}>
      <header className="card__header">
        <h3 className="card__title" id={id ? `${id}-title` : undefined}>
          {title}
        </h3>
        {action}
      </header>
      {description ? <p className="small muted">{description}</p> : null}
      {children}
    </section>
  )
}

export function Field({
  label,
  hint,
  children,
  htmlFor,
}: {
  label: string
  hint?: ReactNode
  children: ReactNode
  htmlFor?: string
}) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {hint ? <span className="field__hint">{hint}</span> : null}
    </div>
  )
}

export function Stat({ value, label, tone }: { value: ReactNode; label: string; tone?: BadgeTone }) {
  return (
    <div className="stat">
      <div className="stat__value" style={tone && tone !== 'neutral' ? { color: `var(--${tone})` } : undefined}>
        {value}
      </div>
      <div className="stat__label">{label}</div>
    </div>
  )
}

/** Renders FTS snippets. Segments are plain strings - no HTML is ever parsed. */
export function Highlighted({ snippet, segments }: { snippet?: string; segments?: Segment[] }) {
  const parts = segments ?? splitHighlights(snippet ?? '')
  return (
    <>
      {parts.map((segment, index) =>
        segment.marked ? <mark key={index}>{segment.text}</mark> : <span key={index}>{segment.text}</span>,
      )}
    </>
  )
}

export function Provenance({
  sourceTitle,
  locator,
  author,
  published,
  extra,
}: {
  sourceTitle: string
  locator?: string
  author?: string | null
  published?: string | null
  extra?: ReactNode
}) {
  return (
    <div className="provenance">
      <span>{sourceTitle}</span>
      {locator ? <span className="provenance__locator">{locator}</span> : null}
      {author ? <span>· {author}</span> : null}
      {published ? <span>· {published}</span> : null}
      {extra}
    </div>
  )
}

export function ChipToggle({
  label,
  pressed,
  onToggle,
  count,
}: {
  label: string
  pressed: boolean
  onToggle: () => void
  count?: number
}) {
  return (
    <button type="button" className="chip" aria-pressed={pressed} onClick={onToggle}>
      {label}
      {count !== undefined ? <span className="faint"> {count}</span> : null}
    </button>
  )
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: Array<{ value: T; label: string }>
  value: T
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function KeyHint({ keys }: { keys: string[] }) {
  return (
    <span className="row" style={{ gap: 4 }}>
      {keys.map((key) => (
        <kbd key={key}>{key}</kbd>
      ))}
    </span>
  )
}
