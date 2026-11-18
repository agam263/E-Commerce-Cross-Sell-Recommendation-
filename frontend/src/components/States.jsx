/** Loading, error and empty states. Every page uses these, never a bare spinner. */
import { CircleAlert, Inbox, RefreshCw } from 'lucide-react'

export function Loading({ label = 'Loading…', rows = 3 }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{label}</p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: Math.min(rows, 4) }).map((_, i) => (
          <div key={i} className="skeleton h-24" />
        ))}
      </div>
      <div className="skeleton h-64" />
    </div>
  )
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="card card-pad" role="alert">
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
          style={{ background: 'var(--bad-weak)', color: 'var(--bad)' }}
        >
          <CircleAlert size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="panel-title">Could not load this view</p>
          <p className="panel-sub break-words">{message}</p>
          {onRetry && (
            <button type="button" className="btn btn-sm mt-3" onClick={onRetry}>
              <RefreshCw size={14} /> Try again
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function EmptyState({ title, hint, icon: Icon = Inbox, action = null, compact = false }) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${compact ? 'py-8' : 'py-14'}`}
    >
      <span
        className="inline-flex h-11 w-11 items-center justify-center rounded-xl"
        style={{ background: 'var(--surface-3)', color: 'var(--text-muted)' }}
      >
        <Icon size={20} />
      </span>
      <p className="mt-3 text-sm font-semibold">{title}</p>
      {hint && (
        <p className="mt-1 max-w-md text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
          {hint}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
