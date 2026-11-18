import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Eye, Search, Share2, ShoppingCart, Sparkles, X } from 'lucide-react'
import { RANKINGS, endpoints } from '../api/client'
import { useApi, useDebounced } from '../lib/useApi'
import { PageHeader, Panel } from '../components/Layout'
import { EmptyState, ErrorState } from '../components/States'
import {
  CategoryChip,
  DerivedCategoryNote,
  ProductPhoto,
} from '../components/ProductTile'
import { StrengthMeter, strengthBand } from '../components/StatTile'
import { AssociationGraph } from '../components/AssociationGraph'
import { Drawer } from '../components/Drawer'
import { dec, int, money, pct } from '../lib/format'

/* ------------------------------------------------------------------ card -- */
function RecommendationCard({ rec, onInspect }) {
  const isRule = rec.source === 'association_rule'
  const band = strengthBand(rec.lift)

  return (
    <article
      className="card flex h-full flex-col p-4"
      style={isRule ? undefined : { borderStyle: 'dashed', borderColor: 'var(--warn)' }}
    >
      <div className="flex items-start gap-3">
        <ProductPhoto category={rec.category} size="lg" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="label-xs">#{rec.rank}</span>
            <span className="num text-xs" style={{ color: 'var(--text-muted)' }}>{rec.stock_code}</span>
          </div>
          <h3 className="mt-0.5 text-sm font-semibold leading-snug" title={rec.product_name}>
            {rec.product_name}
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            {rec.median_unit_price != null && (
              <span className="num text-sm font-semibold" style={{ color: 'var(--accent)' }}>
                {money(rec.median_unit_price)}
              </span>
            )}
            {rec.invoice_count != null && (
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                in {int(rec.invoice_count)} invoices
              </span>
            )}
          </div>
        </div>
      </div>

      {isRule ? (
        <>
          <div className="mt-3 flex items-center justify-between gap-2 rounded-lg px-3 py-2" style={{ background: 'var(--surface-2)' }}>
            <StrengthMeter lift={rec.lift} />
            <span className="num text-sm font-semibold">{dec(rec.lift, 2)}x lift</span>
          </div>

          <dl className="mt-2 grid grid-cols-2 gap-2">
            {[
              ['Confidence', pct(rec.confidence, 1), 'of baskets with the trigger also had this'],
              ['Support', dec(rec.support, 4), 'share of all invoices with both'],
            ].map(([label, value, hint]) => (
              <div key={label} className="rounded-lg px-2.5 py-1.5" style={{ background: 'var(--surface-2)' }}>
                <dt className="label-xs" title={hint}>{label}</dt>
                <dd className="num text-base font-semibold">{value}</dd>
              </div>
            ))}
          </dl>

          <p className="mt-3 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            {rec.explanation}
          </p>

          <div className="mt-auto flex items-center justify-between gap-2 pt-3">
            <span className="num text-[11px]" style={{ color: 'var(--text-muted)' }}>
              {rec.rule_id} · {int(rec.support_count)}/{int(rec.antecedent_count)} invoices
            </span>
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => onInspect(rec)}>
              <Eye size={14} /> Inspect rule
            </button>
          </div>
        </>
      ) : (
        <>
          <span className="chip chip-warn mt-3 self-start">Popularity fallback</span>
          <p className="mt-2 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            {rec.explanation}
          </p>
          <p className="num mt-auto pt-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
            Appears in {pct(rec.popularity_support, 2)} of training invoices · no rule metrics,
            because no rule fired.
          </p>
        </>
      )}
      <span className="sr-only">{band.label}</span>
    </article>
  )
}

/* ------------------------------------------------------------- the page -- */
export default function ProductExplorer() {
  // The basket lives in the query string (?basket=85123A,22423) so a given set
  // of recommendations can be bookmarked, shared or pasted into a ticket.
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [basket, setBasket] = useState(() =>
    (params.get('basket') || '').split(',').map((c) => c.trim()).filter(Boolean),
  )
  const [topK, setTopK] = useState(6)
  const [cohort, setCohort] = useState('all')
  const [ranking, setRanking] = useState('confidence')
  const [onlyWithRules, setOnlyWithRules] = useState(true)
  const [inspecting, setInspecting] = useState(null)
  const debounced = useDebounced(query, 300)

  const search = useApi(
    () => endpoints.products({ search: debounced || undefined, only_with_rules: onlyWithRules, limit: 25 }),
    [debounced, onlyWithRules],
  )
  const health = useApi(() => endpoints.health(), [])

  const payload = useMemo(
    () => ({
      products: basket,
      top_k: Number(topK) || 6,
      cohort,
      rank_by: RANKINGS[ranking].order,
    }),
    [basket, topK, cohort, ranking],
  )

  const recs = useApi(() => endpoints.basketRecommendations(payload), [JSON.stringify(payload)], {
    enabled: basket.length > 0,
  })

  // Details for the products actually in the basket, so the hero can show
  // price and category rather than just a code.
  const basketDetails = useApi(
    () => Promise.all(basket.map((code) => endpoints.product(code))),
    [basket.join(',')],
    { enabled: basket.length > 0 },
  )

  useEffect(() => {
    const next = new URLSearchParams(params)
    if (basket.length) next.set('basket', basket.join(','))
    else next.delete('basket')
    if (next.toString() !== params.toString()) setParams(next, { replace: true })
  }, [basket]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (code) =>
    setBasket((cur) => (cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code]))

  const cohorts = health.data?.cohorts ?? ['all']
  const recommendations = recs.data?.recommendations ?? []
  const ruleBacked = recommendations.filter((r) => r.source === 'association_rule')

  return (
    <>
      <PageHeader
        title="Product Explorer"
        description="Build a basket, then see what the rule set suggests selling alongside it — with the evidence behind every suggestion, and the option to re-rank the same rules the way the PRD specifies."
      />

      <div className="grid min-w-0 gap-4 xl:grid-cols-[21rem_minmax(0,1fr)]">
        {/* ------------------------------------------------- left column -- */}
        <div className="min-w-0 space-y-3">
          <Panel title="Find a product">
            <div className="relative">
              <Search
                size={16}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2"
                style={{ color: 'var(--text-muted)' }}
              />
              <input
                className="input pl-9"
                placeholder="Name or StockCode…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search the product catalog"
              />
            </div>
            <label className="mt-2.5 flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
              <input
                type="checkbox"
                checked={onlyWithRules}
                onChange={(e) => setOnlyWithRules(e.target.checked)}
              />
              Only products that can fire a rule
            </label>

            <div className="mt-3 max-h-[24rem] space-y-1 overflow-y-auto">
              {search.loading && <div className="skeleton h-40" />}
              {search.error && <p className="text-sm" style={{ color: 'var(--bad)' }}>{search.error}</p>}
              {search.data?.items?.length === 0 && (
                <EmptyState compact icon={Search} title="No match" hint={`Nothing matches “${query}”.`} />
              )}
              {search.data?.items?.map((product) => {
                const selected = basket.includes(product.stock_code)
                return (
                  <button
                    key={product.stock_code}
                    type="button"
                    onClick={() => toggle(product.stock_code)}
                    className="flex w-full items-center gap-2.5 rounded-lg p-2 text-left transition-colors"
                    style={{
                      background: selected ? 'var(--accent-weak)' : 'transparent',
                      border: `1px solid ${selected ? 'var(--accent)' : 'transparent'}`,
                    }}
                  >
                    <ProductPhoto category={product.category} size="sm" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{product.product_name}</span>
                      <span className="num block text-[11px]" style={{ color: 'var(--text-muted)' }}>
                        {product.stock_code} · {money(product.median_unit_price)}
                      </span>
                    </span>
                    <span className="num shrink-0 text-xs" style={{ color: 'var(--text-muted)' }}>
                      {int(product.invoice_count)}
                    </span>
                  </button>
                )
              })}
            </div>
            {search.data && (
              <p className="mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
                Showing {search.data.items.length} of {int(search.data.total)} matching products.
              </p>
            )}
            <DerivedCategoryNote className="mt-2" />
          </Panel>

          <Panel title="Serving controls" description="These filter the already-mined rules at serving time; nothing is re-mined.">
            <div className="space-y-3">
              <div>
                <label className="label-xs" htmlFor="ranking">Ranking</label>
                <select
                  id="ranking"
                  className="select mt-1"
                  value={ranking}
                  onChange={(e) => setRanking(e.target.value)}
                >
                  {Object.values(RANKINGS).map((r) => (
                    <option key={r.id} value={r.id}>{r.label}</option>
                  ))}
                </select>
                <p className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                  {RANKINGS[ranking].note}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="label-xs" htmlFor="topk">Top-K</label>
                  <input
                    id="topk"
                    className="input mt-1"
                    type="number"
                    min={1}
                    max={24}
                    value={topK}
                    onChange={(e) => setTopK(e.target.value)}
                  />
                </div>
                <div>
                  <label className="label-xs" htmlFor="cohort">Cohort</label>
                  <select
                    id="cohort"
                    className="select mt-1"
                    value={cohort}
                    onChange={(e) => setCohort(e.target.value)}
                  >
                    {cohorts.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              </div>
            </div>
          </Panel>
        </div>

        {/* ------------------------------------------------ right column -- */}
        <div className="min-w-0 space-y-4">
          <Panel
            title="Current basket"
            actions={
              basket.length > 0 && (
                <button type="button" className="btn btn-sm" onClick={() => setBasket([])}>Clear</button>
              )
            }
          >
            {basket.length === 0 ? (
              <EmptyState
                compact
                icon={ShoppingCart}
                title="Nothing selected yet"
                hint="Pick one or more products on the left. A rule only fires when its whole 'if' side is already in the basket, so adding a second product narrows the suggestions rather than widening them."
              />
            ) : (
              <div className="flex flex-wrap gap-2">
                {(basketDetails.data ?? basket.map((c) => ({ stock_code: c }))).map((p) => (
                  <span
                    key={p.stock_code}
                    className="flex items-center gap-2 rounded-xl py-1.5 pl-1.5 pr-2.5"
                    style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
                  >
                    <ProductPhoto category={p.category} size="sm" />
                    <span className="min-w-0">
                      <span className="block max-w-[14rem] truncate text-sm font-medium">
                        {p.product_name ?? p.stock_code}
                      </span>
                      <span className="num block text-[11px]" style={{ color: 'var(--text-muted)' }}>
                        {p.stock_code}
                        {p.median_unit_price != null ? ` · ${money(p.median_unit_price)}` : ''}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => toggle(p.stock_code)}
                      aria-label={`Remove ${p.stock_code}`}
                      style={{ color: 'var(--text-muted)' }}
                    >
                      <X size={14} />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </Panel>

          {recs.error && <ErrorState message={recs.error} onRetry={recs.reload} />}
          {recs.loading && <div className="skeleton h-72" />}

          {basket.length > 0 && recs.data && (
            <>
              <Panel
                title="How these products connect"
                description="The basket sits at the centre; each spoke is one recommendation."
                actions={
                  <span className="chip chip-accent">
                    <Sparkles size={12} /> {RANKINGS[ranking].label}
                  </span>
                }
              >
                <AssociationGraph
                  centreLabel={recs.data.basket_names?.[0] ?? basket[0]}
                  centreCategory={basketDetails.data?.[0]?.category}
                  edges={ruleBacked}
                  onSelect={(code) => setBasket([code])}
                />
              </Panel>

              <div>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <h2 className="panel-title">
                    {recs.data.count} recommendation{recs.data.count === 1 ? '' : 's'}
                  </h2>
                  <span className="num text-xs" style={{ color: 'var(--text-muted)' }}>
                    rule set {recs.data.ruleset_version} · ranked by{' '}
                    {recs.data.rank_by?.join(' → ')}
                  </span>
                </div>

                {recommendations.length === 0 ? (
                  <Panel>
                    <EmptyState
                      icon={Share2}
                      title="No rule fired for this basket"
                      hint="Every rule needs its whole 'if' side present. Try removing a product, or lowering the thresholds in config and retraining."
                    />
                  </Panel>
                ) : (
                  <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
                    {recommendations.map((rec) => (
                      <RecommendationCard key={rec.stock_code} rec={rec} onInspect={setInspecting} />
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* --------------------------------------------------- rule drawer -- */}
      <Drawer
        open={Boolean(inspecting)}
        onClose={() => setInspecting(null)}
        title={inspecting ? `Rule ${inspecting.rule_id}` : ''}
        subtitle="The exact association behind this recommendation"
      >
        {inspecting && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1 rounded-xl p-3" style={{ background: 'var(--surface-2)' }}>
                <p className="label-xs">If the basket contains</p>
                <p className="mt-1 text-sm font-semibold">
                  {recs.data?.basket_names?.join(', ')}
                </p>
                <p className="num text-xs" style={{ color: 'var(--text-muted)' }}>
                  {inspecting.antecedents?.join(', ')}
                </p>
              </div>
            </div>
            <div className="flex justify-center" style={{ color: 'var(--accent)' }}>↓</div>
            <div className="flex items-center gap-3 rounded-xl p-3" style={{ background: 'var(--accent-weak)' }}>
              <ProductPhoto category={inspecting.category} size="md" />
              <div className="min-w-0">
                <p className="label-xs">Then recommend</p>
                <p className="mt-0.5 text-sm font-semibold">{inspecting.product_name}</p>
                <p className="num text-xs" style={{ color: 'var(--text-muted)' }}>
                  {inspecting.stock_code}
                  {inspecting.median_unit_price != null ? ` · ${money(inspecting.median_unit_price)}` : ''}
                </p>
              </div>
            </div>

            <dl className="grid grid-cols-2 gap-2">
              {[
                ['Support', dec(inspecting.support, 4), 'Share of all invoices containing both sides.'],
                ['Confidence', pct(inspecting.confidence, 1), 'Of invoices with the trigger, the share that also had this.'],
                ['Lift', `${dec(inspecting.lift, 2)}x`, 'How far above chance the pairing is. 1.0 means no association.'],
                ['Leverage', dec(inspecting.leverage, 4), 'Absolute excess co-occurrence over independence.'],
              ].map(([label, value, hint]) => (
                <div key={label} className="card card-tight">
                  <dt className="label-xs">{label}</dt>
                  <dd className="num mt-0.5 text-lg font-semibold">{value}</dd>
                  <dd className="mt-1 text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                    {hint}
                  </dd>
                </div>
              ))}
            </dl>

            <div>
              <p className="label-xs">Evidence</p>
              <p className="mt-1 text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {inspecting.explanation}
              </p>
            </div>

            <div className="rounded-lg p-3 text-xs leading-relaxed" style={{ background: 'var(--surface-2)', color: 'var(--text-secondary)' }}>
              This is historical co-occurrence in one year of one UK gift wholesaler's invoices. It
              is evidence for a merchandising decision, not proof that showing one product causes
              the other to sell.
            </div>

            {inspecting.category && (
              <div>
                <p className="label-xs mb-1">Derived category</p>
                <CategoryChip category={inspecting.category} />
              </div>
            )}
          </div>
        )}
      </Drawer>
    </>
  )
}
