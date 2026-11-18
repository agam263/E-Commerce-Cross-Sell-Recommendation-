import { CircleCheck } from 'lucide-react'
import { endpoints } from '../api/client'
import { useApi } from '../lib/useApi'
import { PageHeader, Panel } from '../components/Layout'
import { ErrorState, Loading } from '../components/States'
import { Meter } from '../components/StatTile'
import { datetime, dec, int, pct } from '../lib/format'

/** Label/value row — the whole page is these, so they share one presentation. */
function Row({ label, value, hint, mono = false }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2" style={{ borderTop: '1px solid var(--border)' }}>
      <div className="min-w-0">
        <dt className="text-sm" style={{ color: 'var(--text-secondary)' }}>{label}</dt>
        {hint && <dd className="text-xs" style={{ color: 'var(--text-muted)' }}>{hint}</dd>}
      </div>
      <dd
        className={`shrink-0 text-right text-sm font-semibold ${mono ? 'num break-all' : ''}`}
        style={mono ? { fontFamily: 'ui-monospace, monospace', maxWidth: '16rem' } : undefined}
      >
        {value}
      </dd>
    </div>
  )
}

export default function ModelInfo() {
  const config = useApi(() => endpoints.config(), [])
  const evaluation = useApi(() => endpoints.evaluation(), [])

  if (config.loading) return <Loading label="Loading model configuration…" rows={3} />
  if (config.error) return <ErrorState message={config.error} onRetry={config.reload} />

  const c = config.data
  const thresholds = c.thresholds ?? {}
  const dataset = c.dataset ?? {}
  const evalData = evaluation.data?.evaluation?.test ?? {}
  const replay = evalData.replay ?? {}
  const audit = evaluation.data?.cleaning_audit ?? []
  const preprocessing = c.preprocessing ?? {}

  return (
    <>
      <PageHeader
        title="Model & Rule Set"
        description="Exactly which data and which thresholds produced the recommendations you are looking at. The same raw file plus the same configuration reproduces this rule set byte for byte."
      >
        <span className="chip chip-accent num">{c.ruleset_version}</span>
      </PageHeader>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Rule set" description="Identity and provenance.">
          <dl className="mt-1">
            <Row label="Version" value={c.ruleset_version} mono />
            <Row label="Built at" value={datetime(c.built_at)} />
            <Row label="Pipeline version" value={c.pipeline_version ?? '—'} />
            <Row label="Config fingerprint" value={c.config_fingerprint ?? '—'} mono />
            <Row label="Cohort rule sets" value={(c.cohorts ?? []).join(', ') || '—'} />
          </dl>
        </Panel>

        <Panel title="Mining thresholds" description="What a pattern had to clear to become a rule.">
          <dl className="mt-1">
            <Row label="Engine" value={thresholds.engine ?? '—'} hint="Own Apriori, verified against mlxtend" />
            <Row label="Min support" value={dec(thresholds.min_support, 4)} hint="Share of training invoices" />
            <Row label="Min confidence" value={pct(thresholds.min_confidence, 0)} />
            <Row label="Min lift" value={`${dec(thresholds.min_lift, 1)}x`} />
            <Row label="Min antecedent count" value={int(thresholds.min_antecedent_count)} hint="Invoices behind the 'if' side" />
            <Row label="Max itemset size" value={int(thresholds.max_itemset_size)} />
          </dl>
        </Panel>

        <Panel title="Serving" description="How candidates become a top-K list.">
          <dl className="mt-1">
            <Row label="Top-K served" value={int(c.recommendation?.top_k)} />
            <Row
              label="Ranking order"
              value={(c.recommendation?.rank_by ?? []).join(' → ')}
              hint="Overridable per request"
            />
            <Row label="No-rule fallback" value={c.recommendation?.fallback ?? '—'} hint="Labelled, never faked metrics" />
          </dl>
          <p className="mt-3 rounded-lg p-2.5 text-xs leading-relaxed" style={{ background: 'var(--surface-2)', color: 'var(--text-secondary)' }}>
            The PRD specifies lift-first ranking. The shipped default is confidence-first because it
            measured better on the validation split (hit rate @5 of 0.181 against 0.157). Both are
            available — the Product Explorer can switch between them live.
          </p>
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="Dataset snapshot" description="The exact bytes the rules were learned from.">
          <dl className="mt-1">
            <Row label="File" value={dataset.name ?? '—'} />
            <Row label="Rows" value={int(dataset.rows)} />
            <Row
              label="Size"
              value={dataset.bytes ? `${dec(dataset.bytes / 1_000_000, 1)} MB` : '—'}
            />
            <Row label="SHA-256" value={dataset.sha256 ?? '—'} mono />
            <Row label="Source" value={dataset.source ?? '—'} />
          </dl>
        </Panel>

        <Panel title="Hold-out evaluation" description="Measured once, on the chronologically last slice the miner never saw.">
          {evaluation.loading ? (
            <div className="skeleton h-40" />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                {[
                  ['Hit rate @5', pct(replay.hit_rate_at_k, 2), 'good'],
                  ['Popularity baseline', pct(replay.popularity_baseline_hit_rate, 2), 'neutral'],
                  ['Uplift', `${dec(replay.uplift_vs_popularity, 2)}x`, 'good'],
                  ['MRR @5', dec(replay.mrr_at_k, 4), 'neutral'],
                ].map(([label, value, tone]) => (
                  <div key={label} className="rounded-lg p-3" style={{ background: 'var(--surface-2)' }}>
                    <p className="label-xs">{label}</p>
                    <p
                      className="num mt-0.5 text-xl font-semibold"
                      style={{ color: tone === 'good' ? 'var(--good)' : 'var(--text-primary)' }}
                    >
                      {value}
                    </p>
                  </div>
                ))}
              </div>
              <div className="mt-4 space-y-3">
                <Meter label="Basket coverage" value={replay.basket_coverage ?? 0} tone="good" />
                <Meter
                  label="Catalog coverage"
                  value={evalData.catalog_coverage?.coverage ?? 0}
                  caption="Products with at least one rule-based recommendation."
                />
              </div>
            </>
          )}
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="Preprocessing policy" description="Decisions applied before a single rule was mined.">
          <dl className="mt-1">
            {Object.entries(preprocessing)
              // List-valued settings (the service-code patterns) are configuration
              // detail, not a policy a reader scans; they stay in config.yaml.
              .filter(([, value]) => !Array.isArray(value) && value !== null)
              .map(([key, value]) => (
                <Row
                  key={key}
                  label={key.replaceAll('_', ' ').replace(/^./, (ch) => ch.toUpperCase())}
                  value={
                    typeof value === 'boolean' ? (
                      value ? (
                        <CircleCheck size={16} style={{ color: 'var(--good)' }} />
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>no</span>
                      )
                    ) : (
                      String(value)
                    )
                  }
                />
              ))}
          </dl>
        </Panel>

        <Panel title="Cleaning audit trail" description="Every row removed from the raw file, and which policy removed it.">
          {audit.length === 0 ? (
            <div className="skeleton h-40" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="th">Stage</th>
                    <th className="th">Removed</th>
                    <th className="th">Remaining</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((stage) => (
                    <tr key={stage.stage}>
                      <td className="td">{stage.stage}</td>
                      <td className="td num" style={{ color: stage.rows_removed ? 'var(--bad)' : 'var(--text-muted)' }}>
                        {stage.rows_removed ? `−${int(stage.rows_removed)}` : '—'}
                      </td>
                      <td className="td num">{int(stage.rows_remaining)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <Panel
        className="mt-4"
        title="Reproduce this rule set"
        description="Same raw file (SHA-256 above) plus the same configuration yields the same ruleset_version and the same rules."
      >
        <pre
          className="overflow-x-auto rounded-lg p-3 text-xs"
          style={{ background: 'var(--surface-2)', color: 'var(--text-secondary)' }}
        >
          {c.reproduce?.command ?? 'python -m crosssell.cli train --config config/config.yaml'}
        </pre>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {Object.entries(c.environment?.packages ?? {}).map(([pkg, version]) => (
            <span key={pkg} className="chip num">{pkg} {version}</span>
          ))}
          {c.environment?.platform && (
            <span className="chip num">{c.environment.platform}</span>
          )}
        </div>
      </Panel>
    </>
  )
}
