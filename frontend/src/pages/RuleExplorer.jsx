import { useMemo, useState } from 'react'
import {
  ArrowRight,
  ArrowUpDown,
  Download,
  Eye,
  Filter,
  Search,
  Table2,
} from 'lucide-react'
import { endpoints } from '../api/client'
import { useApi, useDebounced } from '../lib/useApi'
import { PageHeader, Panel } from '../components/Layout'
import { EmptyState, ErrorState } from '../components/States'
import { StrengthMeter } from '../components/StatTile'
import { ProductPhoto } from '../components/ProductTile'
import { Drawer } from '../components/Drawer'
import { dec, downloadCsv, int, pct } from '../lib/format'

const PAGE_SIZE = 25

const COLUMNS = [
  { key: 'support', label: 'Support', format: (v) => dec(v, 4) },
  { key: 'confidence', label: 'Confidence', format: (v) => pct(v, 1) },
  { key: 'lift', label: 'Lift', format: (v) => `${dec(v, 2)}x` },
]

export default function RuleExplorer() {
  const [search, setSearch] = useState('')
  const [minConfidence, setMinConfidence] = useState('')
  const [minLift, setMinLift] = useState('')
  const [minSupport, setMinSupport] = useState('')
  const [maxAntecedent, setMaxAntecedent] = useState('')
  const [cohort, setCohort] = useState('all')
  const [sortBy, setSortBy] = useState('lift')
  const [order, setOrder] = useState('desc')
  const [page, setPage] = useState(0)
  const [inspecting, setInspecting] = useState(null)

  const debounced = useDebounced(search, 300)

  const params = useMemo(
    () => ({
      search: debounced || undefined,
      min_confidence: minConfidence === '' ? undefined : Number(minConfidence),
      min_lift: minLift === '' ? undefined : Number(minLift),
      min_support: minSupport === '' ? undefined : Number(minSupport),
      max_antecedent_len: maxAntecedent === '' ? undefined : Number(maxAntecedent),
      cohort,
      sort_by: sortBy,
      order,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    [debounced, minConfidence, minLift, minSupport, maxAntecedent, cohort, sortBy, order, page],
  )

  const rules = useApi(() => endpoints.rules(params), [JSON.stringify(params)])
  const health = useApi(() => endpoints.health(), [])

  const total = rules.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const items = rules.data?.items ?? []

  const sortOn = (key) => {
    if (sortBy === key) setOrder((o) => (o === 'desc' ? 'asc' : 'desc'))
    else {
      setSortBy(key)
      setOrder('desc')
    }
    setPage(0)
  }

  const resetFilters = () => {
    setSearch('')
    setMinConfidence('')
    setMinLift('')
    setMinSupport('')
    setMaxAntecedent('')
    setCohort('all')
    setPage(0)
  }

  const exportCsv = async () => {
    // Export what the current filters select, not just the page on screen.
    const all = await endpoints.rules({ ...params, limit: 1000, offset: 0 })
    downloadCsv(
      'association_rules.csv',
      all.items.map((r) => ({
        rule_id: r.rule_id,
        antecedents: r.antecedents.join('|'),
        antecedent_names: r.antecedent_names.join('|'),
        consequents: r.consequents.join('|'),
        consequent_names: r.consequent_names.join('|'),
        support: r.support,
        confidence: r.confidence,
        lift: r.lift,
        leverage: r.leverage,
        support_count: r.support_count,
        antecedent_count: r.antecedent_count,
      })),
    )
  }

  return (
    <>
      <PageHeader
        title="Rule Explorer"
        description="Every association the miner produced, with the numbers that justify it. A rule reads “if the basket already contains the left-hand products, the right-hand product is unusually likely to be there too”."
      >
        <button type="button" className="btn" onClick={exportCsv} disabled={!total}>
          <Download size={15} /> Export CSV
        </button>
      </PageHeader>

      {/* ---------------------------------------------------- how to read -- */}
      <Panel className="mb-4" title="How to read a rule">
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            ['Support', 'How common the combination is overall. Low support means the rule rests on few invoices, so treat it carefully however impressive the other numbers look.'],
            ['Confidence', 'Of the baskets that contained the left-hand side, the share that also contained the right. This is the "how often does this actually happen" number.'],
            ['Lift', 'How much more often than chance. Lift of 1 means no association at all; the mining floor here is 2, so every rule listed is a real association.'],
          ].map(([label, text]) => (
            <div key={label} className="rounded-lg p-3" style={{ background: 'var(--surface-2)' }}>
              <p className="label-xs">{label}</p>
              <p className="mt-1 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {text}
              </p>
            </div>
          ))}
        </div>
      </Panel>

      {/* -------------------------------------------------------- filters -- */}
      <Panel
        className="mb-4"
        title="Filters"
        actions={
          <button type="button" className="btn btn-sm btn-ghost" onClick={resetFilters}>
            <Filter size={14} /> Reset
          </button>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <div className="sm:col-span-2">
            <label className="label-xs" htmlFor="rule-search">Product code or name</label>
            <div className="relative mt-1">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
              <input
                id="rule-search"
                className="input pl-9"
                placeholder="e.g. alarm clock"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(0) }}
              />
            </div>
          </div>
          {[
            ['Min confidence', minConfidence, setMinConfidence, '0.20'],
            ['Min lift', minLift, setMinLift, '3'],
            ['Min support', minSupport, setMinSupport, '0.005'],
          ].map(([label, value, setter, placeholder]) => (
            <div key={label}>
              <label className="label-xs">{label}</label>
              <input
                className="input mt-1"
                type="number"
                step="any"
                min="0"
                placeholder={placeholder}
                value={value}
                onChange={(e) => { setter(e.target.value); setPage(0) }}
              />
            </div>
          ))}
          <div>
            <label className="label-xs" htmlFor="cohort-filter">Cohort</label>
            <select
              id="cohort-filter"
              className="select mt-1"
              value={cohort}
              onChange={(e) => { setCohort(e.target.value); setPage(0) }}
            >
              {(health.data?.cohorts ?? ['all']).map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        </div>
        <p className="mt-2.5 text-xs" style={{ color: 'var(--text-muted)' }}>
          {rules.loading ? 'Filtering…' : `${int(total)} rules match. Select a row to inspect it.`}
        </p>
      </Panel>

      {/* ---------------------------------------------------------- table -- */}
      {rules.error ? (
        <ErrorState message={rules.error} onRetry={rules.reload} />
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="th">If basket contains</th>
                  <th className="th">Then recommend</th>
                  {COLUMNS.map((col) => (
                    <th key={col.key} className="th">
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 uppercase tracking-[0.05em]"
                        onClick={() => sortOn(col.key)}
                        style={{ color: sortBy === col.key ? 'var(--accent-text)' : 'inherit' }}
                      >
                        {col.label}
                        <ArrowUpDown size={11} />
                        {sortBy === col.key && <span>{order === 'desc' ? '↓' : '↑'}</span>}
                      </button>
                    </th>
                  ))}
                  <th className="th">Strength</th>
                  <th className="th">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {rules.loading &&
                  Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i}><td className="td" colSpan={7}><div className="skeleton h-7" /></td></tr>
                  ))}

                {!rules.loading && items.length === 0 && (
                  <tr>
                    <td colSpan={8}>
                      <EmptyState
                        icon={Table2}
                        title="No rule matches these filters"
                        hint="Every filter here narrows an already-mined set. Loosen a threshold, or clear the search."
                        action={<button type="button" className="btn btn-sm" onClick={resetFilters}>Reset filters</button>}
                      />
                    </td>
                  </tr>
                )}

                {!rules.loading && items.map((rule) => (
                  <tr
                    key={rule.rule_id}
                    className="row-hover cursor-pointer"
                    onClick={() => setInspecting(rule)}
                    tabIndex={0}
                    role="button"
                    aria-label={`Inspect rule ${rule.rule_id}`}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        setInspecting(rule)
                      }
                    }}
                  >
                    <td className="td">
                      <span className="flex min-w-0 items-center gap-2.5">
                        <ProductPhoto category={rule.antecedent_categories?.[0]} size="sm" />
                        <span className="min-w-0">
                          <span
                            className="block max-w-[13rem] truncate text-sm font-medium"
                            title={rule.antecedent_names.join(', ')}
                          >
                            {rule.antecedent_names.join(' + ')}
                          </span>
                          <span className="num text-xs" style={{ color: 'var(--text-muted)' }}>
                            {rule.antecedents.join(' + ')}
                          </span>
                        </span>
                      </span>
                    </td>
                    <td className="td">
                      <span className="flex min-w-0 items-center gap-2">
                        <ArrowRight size={13} style={{ color: 'var(--accent)' }} className="shrink-0" />
                        <ProductPhoto category={rule.consequent_categories?.[0]} size="sm" />
                        <span className="min-w-0">
                          <span className="block max-w-[12rem] truncate text-sm font-medium" style={{ color: 'var(--accent-text)' }} title={rule.consequent_names.join(', ')}>
                            {rule.consequent_names.join(', ')}
                          </span>
                          <span className="num text-xs" style={{ color: 'var(--text-muted)' }}>
                            {rule.consequents.join(', ')}
                          </span>
                        </span>
                      </span>
                    </td>
                    {COLUMNS.map((col) => (
                      <td key={col.key} className="td num">{col.format(rule[col.key])}</td>
                    ))}
                    <td className="td"><StrengthMeter lift={rule.lift} /></td>
                    <td className="td">
                      <span className="flex items-center justify-between gap-2">
                        <span
                          className="num text-xs"
                          style={{ color: 'var(--text-muted)' }}
                          title={`${rule.support_count} of ${rule.antecedent_count} invoices containing the trigger`}
                        >
                          {int(rule.support_count)} / {int(rule.antecedent_count)}
                        </span>
                        <Eye size={14} style={{ color: 'var(--accent)' }} aria-hidden="true" />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between gap-3 border-t px-4 py-3" style={{ borderColor: 'var(--border)' }}>
              <button type="button" className="btn btn-sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                Previous
              </button>
              <span className="num text-xs" style={{ color: 'var(--text-muted)' }}>
                Page {page + 1} of {int(pages)}
              </span>
              <button type="button" className="btn btn-sm" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>
                Next
              </button>
            </div>
          )}
        </div>
      )}

      {/* --------------------------------------------------- rule drawer -- */}
      <Drawer
        open={Boolean(inspecting)}
        onClose={() => setInspecting(null)}
        title={inspecting ? `Rule ${inspecting.rule_id}` : ''}
        subtitle="Everything recorded about this association"
      >
        {inspecting && (
          <div className="space-y-4">
            <div className="rounded-xl p-3" style={{ background: 'var(--surface-2)' }}>
              <p className="label-xs">If the basket contains</p>
              {inspecting.antecedent_names.map((name, i) => (
                <span key={i} className="mt-1.5 flex items-center gap-2.5">
                  <ProductPhoto category={inspecting.antecedent_categories?.[i]} size="sm" />
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold">{name}</span>
                    <span className="num block text-xs" style={{ color: 'var(--text-muted)' }}>
                      {inspecting.antecedents[i]}
                    </span>
                  </span>
                </span>
              ))}
            </div>
            <div className="text-center" style={{ color: 'var(--accent)' }}>↓</div>
            <div className="flex items-center gap-3 rounded-xl p-3" style={{ background: 'var(--accent-weak)' }}>
              <ProductPhoto category={inspecting.consequent_categories?.[0]} size="md" />
              <div className="min-w-0">
                <p className="label-xs">Then recommend</p>
                <p className="mt-0.5 text-sm font-semibold">{inspecting.consequent_names.join(', ')}</p>
                <p className="num text-xs" style={{ color: 'var(--text-muted)' }}>{inspecting.consequents.join(', ')}</p>
              </div>
            </div>

            <dl className="grid grid-cols-2 gap-2">
              {[
                ['Support', dec(inspecting.support, 4)],
                ['Confidence', pct(inspecting.confidence, 1)],
                ['Lift', `${dec(inspecting.lift, 2)}x`],
                ['Leverage', dec(inspecting.leverage, 4)],
                ['Conviction', inspecting.conviction == null ? '∞' : dec(inspecting.conviction, 2)],
                ['Antecedent size', int(inspecting.antecedent_len)],
              ].map(([label, value]) => (
                <div key={label} className="card card-tight">
                  <dt className="label-xs">{label}</dt>
                  <dd className="num mt-0.5 text-lg font-semibold">{value}</dd>
                </div>
              ))}
            </dl>

            <div className="rounded-lg p-3" style={{ background: 'var(--surface-2)' }}>
              <p className="label-xs">In plain terms</p>
              <p className="mt-1 text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                Of the {int(inspecting.antecedent_count)} invoices containing{' '}
                {inspecting.antecedent_names.join(' and ')},{' '}
                <strong>{int(inspecting.support_count)}</strong> ({pct(inspecting.confidence, 1)})
                also contained {inspecting.consequent_names.join(', ')}. That is{' '}
                {dec(inspecting.lift, 2)}x more often than this product's overall purchase rate.
              </p>
            </div>

            <div className="flex items-center justify-between rounded-lg p-3" style={{ background: 'var(--surface-2)' }}>
              <span className="label-xs">Strength</span>
              <StrengthMeter lift={inspecting.lift} />
            </div>
          </div>
        )}
      </Drawer>
    </>
  )
}
