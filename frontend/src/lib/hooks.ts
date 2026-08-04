/** Data-loading and interaction hooks shared by the pages. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError } from './api'

export interface AsyncState<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
  setData: (value: T | null) => void
}

/**
 * Run an async loader and expose loading/error/data. `deps` behaves like a
 * `useEffect` dependency list; `reload()` re-runs on demand. Results from a
 * superseded call are discarded so fast filter changes cannot race.
 */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [nonce, setNonce] = useState(0)
  const requestId = useRef(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    const id = ++requestId.current
    let cancelled = false
    setLoading(true)
    loaderRef
      .current()
      .then((value) => {
        if (cancelled || id !== requestId.current) return
        setData(value)
        setError(null)
      })
      .catch((cause: unknown) => {
        if (cancelled || id !== requestId.current) return
        setError(cause instanceof ApiError ? cause.message : String(cause))
      })
      .finally(() => {
        if (!cancelled && id === requestId.current) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  const reload = useCallback(() => setNonce((value) => value + 1), [])
  return { data, error, loading, reload, setData }
}

export function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

/** Persist a small piece of UI state (view mode, panel width) across reloads. */
export function useStoredState<T>(key: string, initial: T): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = window.localStorage.getItem(key)
      return stored === null ? initial : (JSON.parse(stored) as T)
    } catch {
      return initial
    }
  })
  const update = useCallback(
    (next: T) => {
      setValue(next)
      try {
        window.localStorage.setItem(key, JSON.stringify(next))
      } catch {
        /* storage disabled - keep the in-memory value */
      }
    },
    [key],
  )
  return [value, update]
}

export interface Shortcut {
  key: string
  handler: (event: KeyboardEvent) => void
  ctrl?: boolean
  shift?: boolean
  allowInInput?: boolean
  description?: string
}

const EDITABLE = new Set(['INPUT', 'TEXTAREA', 'SELECT'])

export function isEditableTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null
  if (!element) return false
  return EDITABLE.has(element.tagName) || element.isContentEditable === true
}

/** Global keyboard shortcuts. Ignored while typing unless `allowInInput`. */
export function useShortcuts(shortcuts: Shortcut[]): void {
  const ref = useRef(shortcuts)
  ref.current = shortcuts

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      for (const shortcut of ref.current) {
        if (event.key.toLowerCase() !== shortcut.key.toLowerCase()) continue
        if (Boolean(shortcut.ctrl) !== (event.ctrlKey || event.metaKey)) continue
        if (shortcut.shift !== undefined && shortcut.shift !== event.shiftKey) continue
        if (!shortcut.allowInInput && isEditableTarget(event.target)) continue
        event.preventDefault()
        shortcut.handler(event)
        return
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])
}

/** Focus trap + Escape handling for modals. */
export function useDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const node = ref.current
    // Prefer the first control in the dialog *body*: a user who opened a form
    // wants the first field, not the close button that happens to precede it.
    // Every part of the list needs the prefix - `.modal__body a, b` would only
    // scope the first one.
    const parts = ['input', 'textarea', 'select', 'button', '[href]', '[tabindex]:not([tabindex="-1"])']
    const scoped = parts.map((part) => `.modal__body ${part}`).join(', ')
    const focusable =
      node?.querySelector<HTMLElement>(scoped) ?? node?.querySelector<HTMLElement>(parts.join(', '))
    focusable?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !node) return
      const items = Array.from(
        node.querySelectorAll<HTMLElement>(
          'input:not([disabled]), textarea:not([disabled]), select:not([disabled]), button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.offsetParent !== null)
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      document.removeEventListener('keydown', onKeyDown, true)
      previous?.focus?.()
    }
  }, [open, onClose])

  return ref
}

/** Text currently selected inside `container`, with its offset in that text. */
export function useSelectionInside(container: HTMLElement | null) {
  const [selection, setSelection] = useState<{ text: string; offset: number | null } | null>(null)

  useEffect(() => {
    if (!container) return
    const onSelectionChange = () => {
      const current = window.getSelection()
      if (!current || current.isCollapsed || current.rangeCount === 0) {
        setSelection(null)
        return
      }
      const range = current.getRangeAt(0)
      if (!container.contains(range.commonAncestorContainer)) return
      const text = current.toString().trim()
      if (!text) {
        setSelection(null)
        return
      }
      const anchor = (range.startContainer.parentElement as HTMLElement | null)?.closest<HTMLElement>('[data-char-start]')
      const base = anchor ? Number(anchor.dataset.charStart) : Number.NaN
      let offset: number | null = null
      if (!Number.isNaN(base) && anchor) {
        const pre = document.createRange()
        pre.selectNodeContents(anchor)
        pre.setEnd(range.startContainer, range.startOffset)
        offset = base + pre.toString().length
      }
      setSelection({ text, offset })
    }
    document.addEventListener('selectionchange', onSelectionChange)
    return () => document.removeEventListener('selectionchange', onSelectionChange)
  }, [container])

  return selection
}

export function useIsFirstRender(): boolean {
  const first = useRef(true)
  return useMemo(() => {
    if (first.current) {
      first.current = false
      return true
    }
    return false
  }, [])
}
