import { useCallback, useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAsync, useShortcuts, useStoredState } from '../lib/hooks'
import { CommandPalette } from './CommandPalette'
import type { Command } from './CommandPalette'
import { useToast } from './Toasts'

interface NavItem {
  to: string
  label: string
  icon: string
  countKey?: 'needs_review' | 'dossiers' | 'knowledge' | 'sources'
  alert?: boolean
}

const NAV: NavItem[] = [
  { to: '/', label: 'Home', icon: '⌂' },
  { to: '/inbox', label: 'Inbox', icon: '⇩', countKey: 'needs_review', alert: true },
  { to: '/library', label: 'Library', icon: '▤', countKey: 'sources' },
  { to: '/search', label: 'Search', icon: '⌕' },
  { to: '/dossiers', label: 'Dossiers', icon: '❑', countKey: 'dossiers' },
  { to: '/knowledge', label: 'Knowledge', icon: '✦', countKey: 'knowledge' },
  { to: '/compare', label: 'Compare', icon: '⇹' },
  { to: '/review', label: 'Review', icon: '↻' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
]

export function AppShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [quickQuery, setQuickQuery] = useState('')
  const [theme, setTheme] = useStoredState<'dark' | 'light'>('forge.theme', 'dark')
  const [density, setDensity] = useStoredState<'comfortable' | 'compact'>('forge.density', 'comfortable')

  const stats = useAsync(() => api.stats(), [location.pathname])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.dataset.density = density
  }, [theme, density])

  // Keep the UI honest about persisted preferences: the server holds the
  // canonical values, the local copy only avoids a flash on first paint.
  useEffect(() => {
    api
      .settings()
      .then((payload) => {
        const storedTheme = payload.values['ui.theme']
        const storedDensity = payload.values['ui.density']
        if (storedTheme === 'dark' || storedTheme === 'light') setTheme(storedTheme)
        if (storedDensity === 'comfortable' || storedDensity === 'compact') setDensity(storedDensity)
      })
      .catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const toggleTheme = useCallback(() => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    api.updateSettings({ 'ui.theme': next }).catch(() => undefined)
  }, [theme, setTheme])

  const commands = useMemo<Command[]>(
    () => [
      ...NAV.map((item) => ({
        id: `nav-${item.to}`,
        label: `Go to ${item.label}`,
        group: 'Navigate',
        run: () => navigate(item.to),
      })),
      {
        id: 'action-paste',
        label: 'Paste text into the Inbox',
        group: 'Actions',
        run: () => navigate('/inbox?mode=paste'),
      },
      {
        id: 'action-new-dossier',
        label: 'New dossier',
        group: 'Actions',
        run: () => navigate('/dossiers?new=1'),
      },
      {
        id: 'action-new-knowledge',
        label: 'New knowledge object',
        group: 'Actions',
        run: () => navigate('/knowledge?new=1'),
      },
      {
        id: 'action-new-comparison',
        label: 'New comparison',
        group: 'Actions',
        run: () => navigate('/compare?new=1'),
      },
      {
        id: 'action-backup',
        label: 'Create a backup now',
        group: 'Actions',
        run: () => {
          toast.info('Creating backup…')
          api
            .createBackup('manual')
            .then((info) => toast.success(`Backup written: ${info.name}`))
            .catch((error: Error) => toast.error(error.message))
        },
      },
      {
        id: 'action-theme',
        label: `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`,
        group: 'Actions',
        run: toggleTheme,
      },
    ],
    [navigate, theme, toggleTheme, toast],
  )

  useShortcuts([
    { key: 'k', ctrl: true, allowInInput: true, handler: () => setPaletteOpen((open) => !open) },
    {
      key: '/',
      handler: () => {
        const input = document.getElementById('global-search') as HTMLInputElement | null
        input?.focus()
        input?.select()
      },
    },
    { key: 'g', handler: () => navigate('/') },
    { key: 'i', handler: () => navigate('/inbox') },
    { key: 'l', handler: () => navigate('/library') },
    { key: 'd', handler: () => navigate('/dossiers') },
    { key: 'r', handler: () => navigate('/review') },
    { key: '?', handler: () => navigate('/settings#shortcuts') },
  ])

  const counts = stats.data

  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            FG
          </span>
          <span className="brand__name">
            FORGE
            <span className="brand__sub">research intelligence</span>
          </span>
        </div>
        <nav className="nav" aria-label="Primary">
          {NAV.map((item) => {
            const count = item.countKey && counts ? (counts[item.countKey] as number) : undefined
            return (
              <NavLink key={item.to} to={item.to} end={item.to === '/'} className="nav__link">
                <span className="nav__icon" aria-hidden="true">
                  {item.icon}
                </span>
                <span>{item.label}</span>
                {count !== undefined && count > 0 ? (
                  <span className={item.alert ? 'nav__count nav__count--alert' : 'nav__count'}>{count}</span>
                ) : null}
              </NavLink>
            )
          })}
        </nav>
        <div className="sidebar__footer">
          <span>
            <kbd>Ctrl</kbd> <kbd>K</kbd> commands
          </span>
          <span>
            <kbd>/</kbd> search · <kbd>?</kbd> shortcuts
          </span>
          <span className="faint">Local-first · no account · no API key</span>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <form
            className="topbar__search"
            role="search"
            onSubmit={(event) => {
              event.preventDefault()
              if (quickQuery.trim()) navigate(`/search?q=${encodeURIComponent(quickQuery.trim())}`)
            }}
          >
            <input
              id="global-search"
              className="input"
              type="search"
              placeholder="Search sources, excerpts, knowledge, dossiers…  (press / )"
              aria-label="Search everything"
              value={quickQuery}
              onChange={(event) => setQuickQuery(event.target.value)}
            />
          </form>
          <button type="button" className="btn btn--sm" onClick={() => setPaletteOpen(true)}>
            <span aria-hidden="true">⌘</span> Commands
          </button>
          <button
            type="button"
            className="btn btn--sm"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? '☾' : '☀'}
          </button>
        </header>

        <main id="main-content" className="page" tabIndex={-1}>
          <Outlet context={{ reloadStats: stats.reload }} />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />
    </div>
  )
}
