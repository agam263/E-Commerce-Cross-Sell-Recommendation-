/**
 * One derived insight from GET /insights.
 *
 * The prose and the number both come from the API, which builds them from the
 * rule table with fixed templates. Nothing is written here, so the dashboard
 * cannot state a claim the backend did not measure.
 */
import { Lightbulb, ShieldAlert, Target, TrendingUp } from 'lucide-react'
import { dec, int, pct } from '../lib/format'

const KIND = {
  opportunity: { icon: TrendingUp, color: 'var(--good)', wash: 'var(--good-weak)', label: 'Opportunity' },
  coverage: { icon: Target, color: 'var(--accent)', wash: 'var(--accent-weak)', label: 'Coverage' },
  risk: { icon: ShieldAlert, color: 'var(--warn)', wash: 'var(--warn-weak)', label: 'Watch out' },
  pattern: { icon: Lightbulb, color: 'var(--series-2)', wash: 'var(--warn-weak)', label: 'Pattern' },
}

function formatMetric(value, format) {
  if (format === 'percent') return pct(value, 0)
  if (format === 'multiple') return `${dec(value, 1)}x`
  if (format === 'currency') return dec(value, 2)
  return int(value)
}

export function InsightCard({ insight }) {
  const kind = KIND[insight.kind] || KIND.pattern
  const Icon = kind.icon

  return (
    <article className="card card-tight flex h-full flex-col">
      <div className="flex items-start gap-3">
        <span
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
          style={{ background: kind.wash, color: kind.color }}
        >
          <Icon size={17} strokeWidth={2} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="label-xs" style={{ color: kind.color }}>{kind.label}</span>
          </div>
          <h3 className="panel-title mt-0.5 text-sm">{insight.title}</h3>
        </div>
        <div className="shrink-0 text-right">
          <p className="num text-lg font-semibold" style={{ color: kind.color }}>
            {formatMetric(insight.metric_value, insight.metric_format)}
          </p>
          <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
            {insight.metric_label}
          </p>
        </div>
      </div>

      <p className="mt-2.5 text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        {insight.body}
      </p>

      {insight.evidence?.length > 0 && (
        <ul className="mt-auto space-y-1 pt-3">
          {insight.evidence.slice(0, 4).map((row, i) => (
            <li
              key={i}
              className="flex items-center justify-between gap-3 rounded-md px-2 py-1 text-xs"
              style={{ background: 'var(--surface-2)' }}
            >
              <span className="min-w-0 truncate" style={{ color: 'var(--text-secondary)' }}>
                {row.product_name ||
                  `${row.antecedent_name ?? ''} → ${row.consequent_name ?? ''}`}
              </span>
              <span className="num shrink-0 font-semibold" style={{ color: kind.color }}>
                {row.rule_count != null
                  ? `${int(row.rule_count)} ${row.rule_count === 1 ? 'rule' : 'rules'}`
                  : row.lift != null
                    ? `${dec(row.lift, 1)}x`
                    : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
    </article>
  )
}
