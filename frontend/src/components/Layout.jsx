/**
 * Application shell: a dark navigation rail beside a light content area.
 *
 * The rail collapses to a slide-over below `lg`, so the dashboard is usable on
 * a phone rather than merely reflowing into a tall column of nav links.
 */
import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import {
  BookOpen,
  Boxes,
  Calculator,
  ExternalLink,
  LayoutDashboard,
  Menu,
  Moon,
  Settings2,
  Sun,
  Table2,
  X,
} from 'lucide-react'
import { api, endpoints } from '../api/client'
import { useApi } from '../lib/useApi'
import { int } from '../lib/format'

const NAV = [
  { to: '/', label: 'Overview', end: true, hint: 'Business summary', icon: LayoutDashboard },
  { to: '/products', label: 'Product Explorer', hint: 'Cross-sell finder', icon: Boxes },
  { to: '/rules', label: 'Rule Explorer', hint: 'Every association', icon: Table2 },
  { to: '/simulator', label: 'Revenue Simulator', hint: 'Scenario planning', icon: Calculator },
  { to: '/model', label: 'Model & Rule Set', hint: 'Version and config', icon: Settings2 },
  { to: '/help', label: 'Documentation', hint: 'How it works', icon: BookOpen },
]

// localStorage throws, rather than returning null, when site data is blocked
// (private windows, strict privacy settings, some embedded webviews). An
// unguarded read inside a useState initialiser escapes render and mounts the
// entire dashboard as a blank page, so every access is guarded. The theme is a
// convenience; it must never be able to take the app down.
function readTheme() {
  try {
    const saved = localStorage.getItem('crosssell-theme')
    if (saved) return saved === 'dark'
  } catch {
    /* site data unavailable -- fall back to the light default below */
  }
  // Light is the designed default for this dashboard, so the OS preference is
  // deliberately not consulted on a first visit. Dark is one click away and the
  // choice is then remembered.
  return false
}

function ThemeToggle({ compact = false }) {
  const [dark, setDark] = useState(readTheme)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    try {
      localStorage.setItem('crosssell-theme', dark ? 'dark' : 'light')
    } catch {
      /* not persisting the choice is fine; crashing is not */
    }
  }, [dark])

  const Icon = dark ? Sun : Moon
  return (
    <button
      type="button"
      onClick={() => setDark((d) => !d)}
      className="nav-link w-full"
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      <Icon size={17} />
      {!compact && <span>{dark ? 'Light mode' : 'Dark mode'}</span>}
    </button>
  )
}

function RuleCountBadge() {
  const { data } = useApi(() => endpoints.health(), [])
  if (!data?.rules) return null
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold"
      style={{ background: 'rgba(255,255,255,0.08)', color: 'var(--nav-text-active)' }}
    >
      <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: '#34d399' }} />
      {int(data.rules)} rules
    </span>
  )
}

function NavContents({ onNavigate }) {
  return (
    <>
      <div className="px-3 pb-4 pt-5">
        <p className="text-base font-semibold tracking-tight" style={{ color: 'var(--nav-text-active)' }}>
          Cross-Sell Engine
        </p>
        <p className="mt-0.5 text-xs" style={{ color: 'var(--nav-text)' }}>
          Apriori association rules
        </p>
        <div className="mt-3">
          <RuleCountBadge />
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-2">
        {NAV.map(({ to, label, hint, end, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`}
          >
            <Icon size={17} strokeWidth={1.9} className="shrink-0" />
            <span className="min-w-0">
              <span className="block truncate">{label}</span>
              <span className="block truncate text-[11px] opacity-70">{hint}</span>
            </span>
          </NavLink>
        ))}
      </nav>

      <div className="space-y-0.5 px-2 pb-4 pt-3" style={{ borderTop: '1px solid var(--nav-border)' }}>
        <ThemeToggle />
        <a
          className="nav-link"
          href={`${api.defaults.baseURL}/docs`}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink size={17} />
          <span>API reference</span>
        </a>
      </div>
    </>
  )
}

export default function Layout({ children }) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className="flex min-h-full">
      {/* desktop rail */}
      <aside
        className="hidden w-64 shrink-0 flex-col lg:flex"
        style={{
          background: `linear-gradient(180deg, var(--nav-bg) 0%, var(--nav-bg-2) 100%)`,
          position: 'sticky',
          top: 0,
          height: '100vh',
        }}
      >
        <NavContents />
      </aside>

      {/* mobile slide-over */}
      {menuOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0"
            style={{ background: 'rgb(15 23 42 / 0.5)' }}
            onClick={() => setMenuOpen(false)}
          />
          <aside
            className="relative flex h-full w-64 flex-col"
            style={{ background: 'var(--nav-bg)', boxShadow: 'var(--shadow-lg)' }}
          >
            <button
              type="button"
              className="absolute right-2 top-2 rounded-md p-1.5"
              style={{ color: 'var(--nav-text)' }}
              onClick={() => setMenuOpen(false)}
              aria-label="Close navigation"
            >
              <X size={18} />
            </button>
            <NavContents onNavigate={() => setMenuOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* mobile top bar */}
        <header
          className="sticky top-0 z-30 flex items-center gap-3 border-b px-4 py-3 lg:hidden"
          style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
        >
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setMenuOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={18} />
          </button>
          <span className="text-sm font-semibold">Cross-Sell Engine</span>
        </header>

        <main className="w-full min-w-0 max-w-full flex-1 overflow-x-hidden px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
          {children}
        </main>
      </div>
    </div>
  )
}

/** Page title block. `actions` sits on the right at desktop width. */
export function PageHeader({ title, description, children }) {
  return (
    <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        {description && (
          <p className="mt-1 max-w-3xl text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            {description}
          </p>
        )}
      </div>
      {children && <div className="flex shrink-0 flex-wrap items-center gap-2">{children}</div>}
    </header>
  )
}

/** Titled content block used by every page. */
export function Panel({ title, description, actions, children, className = '' }) {
  return (
    <section className={`card card-pad ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            {title && <h2 className="panel-title">{title}</h2>}
            {description && <p className="panel-sub">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  )
}
