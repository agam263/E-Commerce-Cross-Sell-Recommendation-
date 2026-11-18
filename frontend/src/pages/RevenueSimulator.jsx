import { useEffect, useState } from 'react'
import { Calculator, Info, TrendingUp, TriangleAlert } from 'lucide-react'
import { endpoints } from '../api/client'
import { useApi } from '../lib/useApi'
import { PageHeader, Panel } from '../components/Layout'
import { ErrorState } from '../components/States'
import { CategoryBars } from '../components/Charts'
import { dec, int, money, pct } from '../lib/format'

/** Scenario identity: a fixed hue each, so a scenario keeps its colour everywhere. */
const SCENARIO_STYLE = {
  conservative: { color: 'var(--series-2)', wash: 'var(--warn-weak)', label: 'Conservative' },
  base: { color: 'var(--accent)', wash: 'var(--accent-weak)', label: 'Base' },
  optimistic: { color: 'var(--good)', wash: 'var(--good-weak)', label: 'Optimistic' },
}

function ScenarioCard({ scenario, currency, featured }) {
  const style = SCENARIO_STYLE[scenario.name] || SCENARIO_STYLE.base
  return (
    <article
      className="card flex flex-col p-4"
      style={featured ? { borderColor: style.color, boxShadow: 'var(--shadow-md)' } : undefined}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="label-xs" style={{ color: style.color }}>
          {style.label ?? scenario.name}
        </span>
        <span className="chip" style={{ background: style.wash, color: style.color, borderColor: 'transparent' }}>
          {pct(scenario.adoption_rate, 1)} adoption
        </span>
      </div>

      <p className="num mt-3 text-2xl font-semibold tracking-tight" style={{ color: style.color }}>
        {money(scenario.estimated_incremental_revenue, currency)}
      </p>
      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>estimated incremental revenue</p>

      <dl className="mt-3 space-y-1.5 border-t pt-3 text-sm" style={{ borderColor: 'var(--border)' }}>
        <div className="flex justify-between gap-2">
          <dt style={{ color: 'var(--text-secondary)' }}>Eligible orders</dt>
          <dd className="num">{int(scenario.eligible_transactions)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt style={{ color: 'var(--text-secondary)' }}>Extra orders</dt>
          <dd className="num">{dec(scenario.expected_additional_orders, 1)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt style={{ color: 'var(--text-secondary)' }}>Value each</dt>
          <dd className="num">{money(scenario.average_order_value, currency)}</dd>
        </div>
      </dl>
    </article>
  )
}

export default function RevenueSimulator() {
  const defaults = useApi(() => endpoints.stats(), [])
  const [eligible, setEligible] = useState('')
  const [aov, setAov] = useState('')
  const [rates, setRates] = useState({ conservative: 2, base: 5, optimistic: 10 })
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  // Seed the form from the hold-out window, then simulate once so the page is
  // never an empty form.
  useEffect(() => {
    const a = defaults.data?.simulation_defaults?.assumptions
    if (!a || eligible !== '') return
    setEligible(String(a.eligible_transactions ?? ''))
    setAov(String(a.average_order_value ?? ''))
    setResult(defaults.data.simulation_defaults)
  }, [defaults.data]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (event) => {
    event?.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const payload = {
        eligible_transactions: Number(eligible),
        average_order_value: Number(aov),
        scenarios: Object.fromEntries(
          Object.entries(rates).map(([name, value]) => [name, Number(value) / 100]),
        ),
      }
      setResult(await endpoints.simulate(payload))
    } catch (err) {
      setError(err?.response?.data?.detail ?? err.message ?? 'Simulation failed.')
    } finally {
      setBusy(false)
    }
  }

  if (defaults.loading) return <div className="skeleton h-96" />
  if (defaults.error) return <ErrorState message={defaults.error} onRetry={defaults.reload} />

  const currency = result?.assumptions?.currency ?? 'GBP'
  const scenarios = result?.scenarios ?? []
  // A scenario keeps one colour everywhere: the card, the legend dot and the
  // bar. Letting the chart pick its own would mean "base" was indigo in one
  // place and orange in another.
  const chartData = scenarios.map((s) => ({
    name: SCENARIO_STYLE[s.name]?.label ?? s.name,
    revenue: Number(s.estimated_incremental_revenue.toFixed(0)),
    color: SCENARIO_STYLE[s.name]?.color ?? 'var(--accent)',
  }))

  return (
    <>
      <PageHeader
        title="Revenue Simulator"
        description="Translate rule coverage into a planning number: how much additional revenue a cross-sell surface could produce under adoption rates you choose. Every figure here is arithmetic on your assumptions — not a measurement."
      />

      {/* ------------------------------------------------------ disclaimer -- */}
      <div
        className="mb-4 flex items-start gap-3 rounded-xl p-3.5"
        style={{ background: 'var(--warn-weak)', border: '1px solid color-mix(in srgb, var(--warn) 30%, transparent)' }}
      >
        <TriangleAlert size={18} className="mt-0.5 shrink-0" style={{ color: 'var(--warn)' }} />
        <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
          <strong style={{ color: 'var(--warn)' }}>Simulated, not measured.</strong> These are
          estimates under user-supplied assumptions. They are not measured or guaranteed revenue
          uplift — establishing real uplift requires a controlled live experiment.
        </p>
      </div>

      <div className="grid min-w-0 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
        {/* ------------------------------------------------- assumptions -- */}
        <form onSubmit={run} className="space-y-3">
          <Panel title="Assumptions">
            <div className="space-y-3">
              <div>
                <label className="label-xs" htmlFor="eligible">Eligible transactions</label>
                <input
                  id="eligible"
                  className="input mt-1"
                  type="number"
                  min="0"
                  value={eligible}
                  onChange={(e) => setEligible(e.target.value)}
                  required
                />
                <p className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                  Orders the cross-sell could appear on. Default: hold-out invoices × basket coverage.
                </p>
              </div>
              <div>
                <label className="label-xs" htmlFor="aov">Average value of the extra purchase</label>
                <input
                  id="aov"
                  className="input mt-1"
                  type="number"
                  step="0.01"
                  min="0"
                  value={aov}
                  onChange={(e) => setAov(e.target.value)}
                  required
                />
                <p className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                  Default: support-weighted mean value of one purchase of a recommended product.
                </p>
              </div>
            </div>
          </Panel>

          <Panel title="Adoption scenarios" description="The share of eligible orders that take the suggestion.">
            <div className="space-y-2.5">
              {Object.entries(rates).map(([name, value]) => {
                const style = SCENARIO_STYLE[name] || SCENARIO_STYLE.base
                return (
                  <div key={name} className="flex items-center gap-3">
                    <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: style.color }} />
                    <label className="flex-1 text-sm capitalize" htmlFor={`rate-${name}`}>{name}</label>
                    <div className="flex w-24 items-center gap-1">
                      <input
                        id={`rate-${name}`}
                        className="input"
                        type="number"
                        step="0.5"
                        min="0"
                        max="100"
                        value={value}
                        onChange={(e) => setRates((r) => ({ ...r, [name]: e.target.value }))}
                      />
                      <span className="text-sm" style={{ color: 'var(--text-muted)' }}>%</span>
                    </div>
                  </div>
                )
              })}
            </div>
            <button type="submit" className="btn btn-primary mt-4 w-full justify-center" disabled={busy}>
              <Calculator size={15} /> {busy ? 'Running…' : 'Run simulation'}
            </button>
            {error && <p className="mt-2 text-xs" style={{ color: 'var(--bad)' }}>{error}</p>}
          </Panel>
        </form>

        {/* ----------------------------------------------------- results -- */}
        <div className="min-w-0 space-y-4">
          {scenarios.length > 0 && (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                {scenarios.map((s) => (
                  <ScenarioCard key={s.name} scenario={s} currency={currency} featured={s.name === 'base'} />
                ))}
              </div>

              <Panel
                title="Scenario comparison"
                description="Revenue scales linearly with adoption, so the spread between scenarios is entirely a statement about adoption, not about the model."
              >
                <CategoryBars
                  layout="horizontal"
                  data={chartData}
                  valueKey="revenue"
                  height={260}
                  valueFormat={(v) => money(v, currency)}
                />
              </Panel>

              <Panel title="How the number is built">
                <pre
                  className="overflow-x-auto rounded-lg p-3 text-xs leading-relaxed"
                  style={{ background: 'var(--surface-2)', color: 'var(--text-secondary)' }}
                >
{`expected_additional_orders    = eligible_transactions × adoption_rate
estimated_incremental_revenue = expected_additional_orders × average_order_value`}
                </pre>
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr>
                        <th className="th">Scenario</th>
                        <th className="th">Adoption</th>
                        <th className="th">Eligible</th>
                        <th className="th">Extra orders</th>
                        <th className="th">Revenue</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scenarios.map((s) => (
                        <tr key={s.name}>
                          <td className="td capitalize">{s.name}</td>
                          <td className="td num">{pct(s.adoption_rate, 1)}</td>
                          <td className="td num">{int(s.eligible_transactions)}</td>
                          <td className="td num">{dec(s.expected_additional_orders, 1)}</td>
                          <td className="td num font-semibold" style={{ color: 'var(--accent-text)' }}>
                            {money(s.estimated_incremental_revenue, currency)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-3 flex items-start gap-2 text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                  <Info size={14} className="mt-0.5 shrink-0" />
                  Every figure in this table is returned by the API, not recomputed in the browser,
                  so what you see cannot drift from what the backend calculates.
                </p>
              </Panel>

              {result?.disclaimer && (
                <p className="flex items-start gap-2 text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                  <TrendingUp size={14} className="mt-0.5 shrink-0" />
                  {result.disclaimer}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </>
  )
}
