/**
 * KPI presentation.
 *
 * A number on its own is not an insight, so every tile carries a label, a
 * formatted value and a one-line statement of what it actually measures.
 */
import { categoryStyle } from '../lib/categories'

export function KpiCard({ icon: Icon, label, value, meaning, tone = 'neutral', foot = null }) {
  const toneColor = {
    neutral: 'var(--accent)',
    good: 'var(--good)',
    warn: 'var(--warn)',
    bad: 'var(--bad)',
  }[tone]
  const toneWash = {
    neutral: 'var(--accent-weak)',
    good: 'var(--good-weak)',
    warn: 'var(--warn-weak)',
    bad: 'var(--bad-weak)',
  }[tone]

  return (
    <div className="card card-tight flex flex-col">
      <div className="flex items-center gap-2.5">
        {Icon && (
          <span
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
            style={{ background: toneWash, color: toneColor }}
          >
            <Icon size={16} strokeWidth={2} />
          </span>
        )}
        <p className="label-xs">{label}</p>
      </div>
      <p className="num mt-2.5 text-2xl font-semibold tracking-tight" style={{ color: toneColor }}>
        {value}
      </p>
      {meaning && (
        <p className="mt-1 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
          {meaning}
        </p>
      )}
      {foot && <div className="mt-auto pt-2.5">{foot}</div>}
    </div>
  )
}

/** Horizontal progress bar for a 0..1 share. */
export function Meter({ label, value, caption, tone = 'accent' }) {
  const pctValue = Math.max(0, Math.min(1, Number(value) || 0))
  const color = { accent: 'var(--accent)', good: 'var(--good)', warn: 'var(--warn)' }[tone]
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="label-xs">{label}</span>
        <span className="num text-sm font-semibold">{(pctValue * 100).toFixed(1)}%</span>
      </div>
      <div
        className="mt-1.5 h-2 w-full overflow-hidden rounded-full"
        style={{ background: 'var(--surface-3)' }}
        role="meter"
        aria-valuenow={Number((pctValue * 100).toFixed(1))}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div className="h-full rounded-full" style={{ width: `${pctValue * 100}%`, background: color }} />
      </div>
      {caption && (
        <p className="mt-1 text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {caption}
        </p>
      )}
    </div>
  )
}

/**
 * Qualitative strength band for a rule.
 *
 * Lift is the axis: 1 means "no better than chance". The bands are a reading
 * aid over the real number, which is always shown next to them.
 */
export function strengthBand(lift) {
  const value = Number(lift)
  if (!Number.isFinite(value)) return { label: 'No rule', tone: 'muted', step: 0 }
  if (value >= 20) return { label: 'Exceptional', tone: 'good', step: 4 }
  if (value >= 8) return { label: 'Strong', tone: 'good', step: 3 }
  if (value >= 3) return { label: 'Moderate', tone: 'accent', step: 2 }
  return { label: 'Marginal', tone: 'warn', step: 1 }
}

export function StrengthMeter({ lift, showLabel = true }) {
  const band = strengthBand(lift)
  const color = {
    good: 'var(--good)',
    accent: 'var(--accent)',
    warn: 'var(--warn)',
    muted: 'var(--text-muted)',
  }[band.tone]
  return (
    <span className="inline-flex items-center gap-2" title={`Lift ${Number(lift).toFixed(2)}x`}>
      <span className="inline-flex items-end gap-[2px]" aria-hidden="true">
        {[1, 2, 3, 4].map((step) => (
          <span
            key={step}
            className="w-[3px] rounded-full"
            style={{
              height: `${4 + step * 2.5}px`,
              background: step <= band.step ? color : 'var(--surface-3)',
            }}
          />
        ))}
      </span>
      {showLabel && (
        <span className="text-xs font-semibold" style={{ color }}>
          {band.label}
        </span>
      )}
    </span>
  )
}

/** Compact product identity line used in tables and drawers. */
export function ProductLine({ code, name, category, tile: Tile = null, size = 'sm' }) {
  const { hue } = categoryStyle(category)
  return (
    <span className="flex min-w-0 items-center gap-2.5">
      {Tile && <Tile category={category} size={size} />}
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium" title={name}>
          {name}
        </span>
        <span className="num block text-xs" style={{ color: hue }}>
          {code}
        </span>
      </span>
    </span>
  )
}
