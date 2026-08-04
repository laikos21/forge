import { useRef, useState } from 'react'
import { useToast } from '../components/Toasts'
import { Badge, EmptyState, ErrorState, Field, Loading, Section } from '../components/ui'
import { api } from '../lib/api'
import { formatBytes, formatDateTime, formatNumber, titleCase } from '../lib/format'
import { useAsync } from '../lib/hooks'

const SHORTCUTS: Array<[string, string]> = [
  ['Ctrl / ⌘ + K', 'Command palette'],
  ['/', 'Focus the global search box'],
  ['g', 'Go home'],
  ['i', 'Go to the Inbox'],
  ['l', 'Go to the Library'],
  ['d', 'Go to Dossiers'],
  ['r', 'Go to the daily Review'],
  ['Esc', 'Close a dialog'],
]

export function SettingsPage() {
  const toast = useToast()
  const settings = useAsync(() => api.settings(), [])
  const system = useAsync(() => api.systemInfo(), [])
  const backups = useAsync(() => api.backups(), [])
  const intelligence = useAsync(() => api.intelligenceStatus(), [])
  const [integrity, setIntegrity] = useState<Awaited<ReturnType<typeof api.integrity>> | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const restoreInput = useRef<HTMLInputElement>(null)

  const save = async (key: string, value: unknown) => {
    try {
      const updated = await api.updateSettings({ [key]: value })
      settings.setData(updated)
      system.reload()
      if (key === 'ui.theme') document.documentElement.dataset.theme = String(value)
      if (key === 'ui.density') document.documentElement.dataset.density = String(value)
      toast.success('Setting saved.')
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const run = async (label: string, action: () => Promise<unknown>, message: string) => {
    setBusy(label)
    try {
      await action()
      toast.success(message)
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setBusy(null)
    }
  }

  if (settings.loading && !settings.data) return <Loading label="Loading settings" rows={5} />
  if (settings.error) return <ErrorState message={settings.error} onRetry={settings.reload} />
  if (!settings.data) return null

  const groups = settings.data.schema.reduce<Record<string, typeof settings.data.schema>>((accumulator, item) => {
    ;(accumulator[item.group] ??= []).push(item)
    return accumulator
  }, {})
  const values = settings.data.values

  return (
    <div className="stack">
      <header className="page__header">
        <div className="page__title">
          <h1>Settings</h1>
          <p className="page__subtitle">
            Preferences are stored in your local database. Paths and limits come from environment variables and are
            shown here read-only.
          </p>
        </div>
        <div className="page__actions">
          <button
            type="button"
            className="btn"
            onClick={() =>
              void run('reset', async () => {
                const reset = await api.resetSettings()
                settings.setData(reset)
              }, 'Settings reset to defaults.')
            }
          >
            Reset to defaults
          </button>
        </div>
      </header>

      <div className="grid grid--2">
        {Object.entries(groups).map(([group, items]) => (
          <Section key={group} title={group}>
            {items.map((item) => (
              <Field key={item.key} label={item.label} hint={item.help} htmlFor={`setting-${item.key}`}>
                {item.type === 'bool' ? (
                  <label className="checkbox">
                    <input
                      id={`setting-${item.key}`}
                      type="checkbox"
                      checked={Boolean(values[item.key])}
                      onChange={(event) => void save(item.key, event.target.checked)}
                    />
                    {values[item.key] ? 'Enabled' : 'Disabled'}
                  </label>
                ) : item.type === 'choice' ? (
                  <select
                    id={`setting-${item.key}`}
                    className="select"
                    value={String(values[item.key])}
                    onChange={(event) => void save(item.key, event.target.value)}
                  >
                    {item.choices.map((choice) => (
                      <option key={choice} value={choice}>
                        {titleCase(choice)}
                      </option>
                    ))}
                  </select>
                ) : item.type === 'list' ? (
                  <input
                    id={`setting-${item.key}`}
                    className="input"
                    defaultValue={(values[item.key] as string[]).join(', ')}
                    onBlur={(event) =>
                      void save(
                        item.key,
                        event.target.value
                          .split(',')
                          .map((value) => value.trim())
                          .filter(Boolean),
                      )
                    }
                  />
                ) : (
                  <input
                    id={`setting-${item.key}`}
                    className="input"
                    defaultValue={String(values[item.key] ?? '')}
                    onBlur={(event) => void save(item.key, event.target.value)}
                  />
                )}
              </Field>
            ))}
          </Section>
        ))}
      </div>

      <Section title="Local intelligence" description="Optional. FORGE never requires a model, an account or a key.">
        {system.data ? (
          <ul className="list">
            <li className="list__item">
              <div className="list__main">
                <span className="list__title">
                  Provider: {intelligence.data?.provider.name ?? system.data.llm.name}{' '}
                  <Badge tone={(intelligence.data?.provider.available ?? false) ? 'success' : 'neutral'}>
                    {(intelligence.data?.provider.available ?? false) ? 'available' : 'unavailable'}
                  </Badge>
                </span>
                <span className="list__meta">
                  {intelligence.data?.provider.detail ?? system.data.llm.detail}
                </span>
                {(intelligence.data?.provider.models.length ?? 0) > 0 ? (
                  <span className="list__meta">
                    Installed models: {intelligence.data?.provider.models.join(', ')}
                  </span>
                ) : null}
              </div>
              <button
                type="button"
                className="btn btn--sm"
                disabled={busy === 'probe'}
                onClick={() =>
                  void run('probe', async () => {
                    intelligence.setData(await api.intelligenceStatus(true))
                  }, 'Provider re-checked.')
                }
              >
                {busy === 'probe' ? 'Checking…' : 'Re-check'}
              </button>
            </li>
            <li className="list__item">
              <div className="list__main">
                <span className="list__title">
                  Semantic search{' '}
                  <Badge tone={system.data.semantic.available ? 'success' : 'neutral'}>
                    {system.data.semantic.enabled ? 'enabled' : 'disabled'}
                  </Badge>
                </span>
                <span className="list__meta">{system.data.semantic.detail}</span>
              </div>
              <div className="btn-group">
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={!system.data.semantic.enabled || busy !== null}
                  onClick={() =>
                    void run('semantic', async () => {
                      const result = await api.buildSemanticIndex()
                      toast.info(result.detail)
                      system.reload()
                    }, 'Semantic index updated.')
                  }
                >
                  Build index
                </button>
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={busy !== null}
                  onClick={() =>
                    void run('semantic-clear', async () => {
                      await api.clearSemanticIndex()
                      system.reload()
                    }, 'Semantic index cleared.')
                  }
                >
                  Clear index
                </button>
              </div>
            </li>
            <li className="list__item">
              <div className="list__main">
                <span className="list__title">
                  OCR{' '}
                  <Badge tone={system.data.ocr.available ? 'success' : 'neutral'}>
                    {system.data.ocr.available ? 'available' : 'not installed'}
                  </Badge>
                </span>
                <span className="list__meta">{system.data.ocr.detail}</span>
              </div>
            </li>
          </ul>
        ) : (
          <Loading label="Checking local providers" rows={2} />
        )}
      </Section>

      <div className="grid grid--2">
        <Section
          title="Backups"
          action={
            <div className="btn-group">
              <button
                type="button"
                className="btn btn--sm btn--primary"
                disabled={busy !== null}
                onClick={() =>
                  void run('backup', async () => {
                    await api.createBackup('manual')
                    backups.reload()
                  }, 'Backup created.')
                }
              >
                Create backup
              </button>
              <button type="button" className="btn btn--sm" onClick={() => restoreInput.current?.click()}>
                Restore from file
              </button>
              <input
                ref={restoreInput}
                type="file"
                accept=".zip"
                hidden
                aria-label="Restore from a backup archive"
                onChange={async (event) => {
                  const file = event.target.files?.[0]
                  event.target.value = ''
                  if (!file) return
                  if (!window.confirm(`Restore from ${file.name}? Your current data is backed up first.`)) return
                  await run('restore', async () => {
                    await api.restoreUpload(file)
                    backups.reload()
                    system.reload()
                  }, 'Restore complete.')
                }}
              />
            </div>
          }
        >
          {backups.data?.items.length === 0 ? (
            <EmptyState
              icon="⛁"
              title="No backups yet"
              body="A backup is a single zip with the database, every original file and a portable JSON export."
            />
          ) : (
            <ul className="list">
              {(backups.data?.items ?? []).map((backup) => (
                <li key={backup.name} className="list__item">
                  <div className="list__main">
                    <span className="list__title">{backup.name}</span>
                    <span className="list__meta">
                      <span>{formatBytes(backup.size_bytes)}</span>
                      <span>{formatDateTime(backup.created_at)}</span>
                      {backup.manifest.counts ? (
                        <span>{formatNumber(backup.manifest.counts.source ?? 0)} sources</span>
                      ) : null}
                      {backup.manifest.file_count !== undefined ? (
                        <span>{backup.manifest.file_count} files</span>
                      ) : null}
                    </span>
                  </div>
                  <div className="btn-group">
                    <a className="btn btn--sm" href={api.backupDownloadUrl(backup.name)}>
                      Download
                    </a>
                    <button
                      type="button"
                      className="btn btn--sm"
                      disabled={busy !== null}
                      onClick={() => {
                        if (!window.confirm(`Restore ${backup.name}? Current data is backed up first.`)) return
                        void run('restore', async () => {
                          await api.restoreBackup(backup.name)
                          backups.reload()
                          system.reload()
                        }, 'Restore complete.')
                      }}
                    >
                      Restore
                    </button>
                    <button
                      type="button"
                      className="btn btn--sm btn--danger"
                      onClick={() => {
                        if (!window.confirm(`Delete ${backup.name}?`)) return
                        void run('delete-backup', async () => {
                          await api.deleteBackup(backup.name)
                          backups.reload()
                        }, 'Backup deleted.')
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Data and maintenance">
          <div className="btn-group" style={{ marginBottom: 12 }}>
            <a className="btn btn--sm" href={api.exportJsonUrl}>
              Export everything as JSON
            </a>
            <button
              type="button"
              className="btn btn--sm"
              disabled={busy !== null}
              onClick={() =>
                void run('reindex', async () => {
                  const result = await api.reindex()
                  toast.info(`${formatNumber(result.total)} objects indexed.`)
                  system.reload()
                }, 'Search index rebuilt.')
              }
            >
              Rebuild search index
            </button>
            <button
              type="button"
              className="btn btn--sm"
              disabled={busy !== null}
              onClick={() => void run('integrity', async () => setIntegrity(await api.integrity()), 'Integrity check finished.')}
            >
              Check integrity
            </button>
            <button
              type="button"
              className="btn btn--sm"
              disabled={busy !== null}
              onClick={() =>
                void run('seed', async () => {
                  const result = await api.seed(true)
                  toast.info(String(result.status))
                  system.reload()
                }, 'Demonstration data loaded.')
              }
            >
              Load demo data
            </button>
            <button
              type="button"
              className="btn btn--sm btn--danger"
              disabled={busy !== null}
              onClick={() => {
                if (!window.confirm('Remove every object marked as demonstration content?')) return
                void run('clear-demo', async () => {
                  await api.clearDemo()
                  system.reload()
                }, 'Demonstration data removed.')
              }}
            >
              Remove demo data
            </button>
          </div>

          {integrity ? (
            <div className={integrity.healthy ? 'notice' : 'notice notice--warning'}>
              <strong>{integrity.healthy ? 'Everything checks out' : 'Issues found'}</strong>
              <ul className="small" style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                <li>
                  Index: {formatNumber(integrity.index.entries)} entries, {formatNumber(integrity.index.expected)}{' '}
                  expected
                </li>
                <li>{integrity.dangling_references.length} dangling references</li>
                <li>{integrity.missing_original_files.length} missing original files</li>
              </ul>
            </div>
          ) : null}

          {system.data ? (
            <ul className="list" style={{ marginTop: 12 }}>
              <li className="list__item">
                <div className="list__main">
                  <span className="list__title mono xs">{system.data.data_dir}</span>
                  <span className="list__meta">Data directory (FORGE_DATA_DIR)</span>
                </div>
              </li>
              <li className="list__item">
                <div className="list__main">
                  <span className="list__title">
                    {formatBytes(system.data.storage.database_bytes)} database ·{' '}
                    {formatBytes(system.data.storage.total_bytes)} originals ({system.data.storage.file_count} files)
                  </span>
                  <span className="list__meta">Local storage in use</span>
                </div>
              </li>
              <li className="list__item">
                <div className="list__main">
                  <span className="list__title">
                    FORGE {system.data.version} · Python {system.data.python} · migration{' '}
                    {system.data.migration.current}
                  </span>
                  <span className="list__meta">
                    {formatNumber(system.data.index_size)} indexed objects · uploads limited to{' '}
                    {system.data.max_upload_mb} MB
                  </span>
                </div>
              </li>
            </ul>
          ) : null}
        </Section>
      </div>

      <Section title="Keyboard shortcuts" id="shortcuts">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 160 }}>Keys</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {SHORTCUTS.map(([keys, action]) => (
                <tr key={keys}>
                  <td>
                    <kbd>{keys}</kbd>
                  </td>
                  <td>{action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  )
}
