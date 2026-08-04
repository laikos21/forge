import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useDebounced } from '../lib/hooks'
import type { SearchHit } from '../lib/types'

export interface Command {
  id: string
  label: string
  hint?: string
  group: string
  run: () => void
}

/**
 * Ctrl/Cmd+K palette: navigation and actions first, then live search results
 * from the same FTS index the Search page uses.
 */
export function CommandPalette({
  open,
  onClose,
  commands,
}: {
  open: boolean
  onClose: () => void
  commands: Command[]
}) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const [hits, setHits] = useState<SearchHit[]>([])
  const debounced = useDebounced(query, 200)
  const listRef = useRef<HTMLUListElement>(null)

  useEffect(() => {
    if (!open) {
      setQuery('')
      setActive(0)
      setHits([])
    }
  }, [open])

  useEffect(() => {
    let cancelled = false
    if (!open || debounced.trim().length < 2) {
      setHits([])
      return
    }
    api
      .search({ q: debounced, limit: 6 })
      .then((response) => {
        if (!cancelled) setHits(response.results)
      })
      .catch(() => {
        if (!cancelled) setHits([])
      })
    return () => {
      cancelled = true
    }
  }, [debounced, open])

  const filteredCommands = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return commands
    return commands.filter(
      (command) =>
        command.label.toLowerCase().includes(needle) || command.group.toLowerCase().includes(needle),
    )
  }, [commands, query])

  const searchCommands: Command[] = hits.map((hit) => ({
    id: `hit-${hit.ref_type}-${hit.ref_id}`,
    label: hit.title || hit.snippet.slice(0, 70),
    hint: hit.subtitle,
    group: 'Search results',
    run: () => {
      if (hit.ref_type === 'source') navigate(`/library/${hit.ref_id}`)
      else if (hit.ref_type === 'excerpt' && hit.source_id) navigate(`/library/${hit.source_id}`)
      else if (hit.ref_type === 'dossier') navigate(`/dossiers/${hit.ref_id}`)
      else if (hit.ref_type === 'knowledge') navigate(`/knowledge?focus=${hit.ref_id}`)
      else navigate(`/search?q=${encodeURIComponent(query)}`)
    },
  }))

  const all = [...filteredCommands, ...searchCommands]
  const clamped = Math.min(active, Math.max(all.length - 1, 0))

  useEffect(() => {
    const node = listRef.current?.querySelector<HTMLElement>('[aria-selected="true"]')
    node?.scrollIntoView({ block: 'nearest' })
  }, [clamped, all.length])

  if (!open) return null

  const run = (command: Command) => {
    command.run()
    onClose()
  }

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label="Command palette">
        <input
          className="palette__input"
          autoFocus
          placeholder="Search everything, or jump to a screen…"
          aria-label="Command palette input"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value)
            setActive(0)
          }}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') {
              event.preventDefault()
              setActive((value) => Math.min(value + 1, all.length - 1))
            } else if (event.key === 'ArrowUp') {
              event.preventDefault()
              setActive((value) => Math.max(value - 1, 0))
            } else if (event.key === 'Enter') {
              event.preventDefault()
              const command = all[clamped]
              if (command) run(command)
              else if (query.trim()) {
                navigate(`/search?q=${encodeURIComponent(query.trim())}`)
                onClose()
              }
            } else if (event.key === 'Escape') {
              onClose()
            }
          }}
        />
        <ul className="palette__results" role="listbox" aria-label="Commands" ref={listRef}>
          {all.length === 0 ? (
            <li className="palette__item faint">
              Press <kbd>Enter</kbd> to run a full search for “{query}”
            </li>
          ) : null}
          {all.map((command, index) => {
            const previous = all[index - 1]
            const showGroup = !previous || previous.group !== command.group
            return (
              <li key={command.id}>
                {showGroup ? (
                  <div className="xs faint" style={{ padding: '8px 12px 2px' }}>
                    {command.group}
                  </div>
                ) : null}
                <div
                  className="palette__item"
                  role="option"
                  aria-selected={index === clamped}
                  onMouseEnter={() => setActive(index)}
                  onMouseDown={(event) => {
                    event.preventDefault()
                    run(command)
                  }}
                >
                  <span>{command.label}</span>
                  {command.hint ? <span className="xs faint">{command.hint}</span> : null}
                  {index === clamped ? (
                    <span className="palette__kbd">
                      <kbd>↵</kbd>
                    </span>
                  ) : null}
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
