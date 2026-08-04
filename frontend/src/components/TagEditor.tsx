import { useState } from 'react'
import { parseTagInput } from '../lib/format'
import type { Tag } from '../lib/types'

/**
 * Inline tag editor. Saves through the callback the parent provides, so the
 * component itself stays free of API knowledge.
 */
export function TagEditor({
  tags,
  onSave,
  disabled = false,
  label = 'Tags',
}: {
  tags: Tag[]
  onSave: (names: string[]) => Promise<void> | void
  disabled?: boolean
  label?: string
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const start = () => {
    setDraft(tags.map((tag) => tag.name).join(', '))
    setEditing(true)
  }

  const commit = async () => {
    setSaving(true)
    try {
      await onSave(parseTagInput(draft))
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  if (editing) {
    return (
      <div className="row" style={{ gap: 6 }}>
        <input
          className="input"
          value={draft}
          autoFocus
          aria-label={`${label} (comma separated)`}
          placeholder="earnings, ai-compute"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') void commit()
            if (event.key === 'Escape') setEditing(false)
          }}
          style={{ maxWidth: 320 }}
        />
        <button type="button" className="btn btn--primary btn--sm" onClick={() => void commit()} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(false)}>
          Cancel
        </button>
      </div>
    )
  }

  return (
    <div className="tag-list">
      {tags.length === 0 ? <span className="xs faint">No tags</span> : null}
      {tags.map((tag) => (
        <span key={tag.id} className="tag">
          {tag.name}
        </span>
      ))}
      {!disabled ? (
        <button type="button" className="btn btn--ghost btn--sm" onClick={start}>
          {tags.length ? 'Edit tags' : 'Add tags'}
        </button>
      ) : null}
    </div>
  )
}
