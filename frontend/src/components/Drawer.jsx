/** Right-hand detail panel. Used to inspect a single association rule. */
import { useEffect } from 'react'
import { X } from 'lucide-react'

export function Drawer({ open, title, subtitle, onClose, children }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={title}>
      <button
        type="button"
        aria-label="Close"
        className="absolute inset-0 cursor-default"
        style={{ background: 'rgb(15 23 42 / 0.45)' }}
        onClick={onClose}
      />
      <aside
        className="relative flex h-full w-full max-w-lg flex-col overflow-y-auto"
        style={{ background: 'var(--surface)', boxShadow: 'var(--shadow-lg)' }}
      >
        <header
          className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b px-5 py-4"
          style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
        >
          <div className="min-w-0">
            <h2 className="panel-title">{title}</h2>
            {subtitle && <p className="panel-sub">{subtitle}</p>}
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </header>
        <div className="px-5 py-4">{children}</div>
      </aside>
    </div>
  )
}
