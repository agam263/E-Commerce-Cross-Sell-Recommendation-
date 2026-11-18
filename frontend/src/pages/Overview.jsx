import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Boxes,
  Layers,
  Percent,
  Receipt,
  ShoppingCart,
  Target,
  TrendingUp,
} from 'lucide-react'
import { endpoints } from '../api/client'
import { useApi } from '../lib/useApi'
import { PageHeader, Panel } from '../components/Layout'
import { ErrorState, Loading } from '../components/States'
import { KpiCard, Meter } from '../components/StatTile'
import { CategoryBars, Donut, MetricHistogram } from '../components/Charts'
import { InsightCard } from '../components/InsightCard'
import { DerivedCategoryNote, ProductPhoto } from '../components/ProductTile'
import { Sparkbar } from '../components/Charts'
import { dec, day, int, money, pct } from '../lib/format'

export default function Overview() {
  const stats = useApi(() => endpoints.stats(), [])
  const insights = useApi(() => endpoints.insights(), [])

  if (stats.loading) return <Loading label="Loading rule-set statistics…" rows={4} />
  if (stats.error) return <ErrorState message={stats.error} onRetry={stats.reload} />

  const data = stats.data
  const k = data.kpis
  const hist = data.metric_histograms || {}
  const perProduct = k.rules_per_product

  // One direction per product pair: a strong pair always yields A->B and B->A
  // with identical lift, so an undeduplicated chart is half redundant.
  const seen = new Set()
  const topPairs = (data.top_rules || [])
    .slice()
    .sort((a, b) => b.lift - a.lift || b.confidence - a.confidence)
    .filter((rule) => {
      const key = [...rule.antecedents, ...rule.consequents].sort().join('|')
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .slice(0, 6)
    .map((rule) => ({
      name: `${rule.antecedent_names[0] ?? ''} → ${rule.consequent_names[0] ?? ''}`,
      lift: Number(rule.lift.toFixed(2)),
    }))

  const topProducts = (data.top_products || []).slice(0, 8)
  const maxInvoices = Math.max(1, ...topProducts.map((p) => p.invoice_count || 0))

  const withRules = k.products_with_recommendation || 0
  const withoutRules = Math.max(0, (k.products_in_rule_set || 0) - withRules)

  const scenarios = data.simulation_defaults?.scenarios || []
  const scenarioBars = scenarios.map((s) => ({
    name: s.scenario,
    revenue: Number(s.estimated_incremental_revenue?.toFixed?.(0) ?? 0),
    base: s.scenario === 'base',
  }))

  return (
    <>
      <PageHeader
        title="Cross-sell overview"
        description={`What the engine learned from ${int(k.total_invoices)} transactions between ${day(k.date_min)} and ${day(k.date_max)}, and how well it holds up on data it never saw.`}
      >
        <Link className="btn" to="/rules">Browse rules</Link>
        <Link className="btn btn-primary" to="/products">
          Find cross-sells <ArrowRight size={15} />
        </Link>
      </PageHeader>

      {/* ---------------------------------------------------------- KPIs -- */}
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        <KpiCard
          icon={Receipt}
          label="Transactions"
          value={int(k.total_invoices)}
          meaning="Invoices in the cleaned dataset the rules were learned from."
        />
        <KpiCard
          icon={ShoppingCart}
          label="Products"
          value={int(k.catalog_products)}
          meaning={`${int(k.products_in_rule_set)} met the minimum-invoice bar for mining.`}
        />
        <KpiCard
          icon={Layers}
          label="Frequent itemsets"
          value={int(k.frequent_itemsets)}
          meaning="Product combinations that clear the minimum support threshold."
        />
        <KpiCard
          icon={Boxes}
          label="Association rules"
          value={int(k.rules)}
          meaning="Directional 'if basket has A, suggest B' statements."
        />
        <KpiCard
          icon={Target}
          label="Recommendation coverage"
          value={pct(k.catalog_coverage, 1)}
          tone="good"
          meaning={`${int(withRules)} products can fire at least one rule.`}
        />
        <KpiCard
          icon={Percent}
          label="Avg confidence / lift"
          value={`${pct(k.avg_confidence, 1)} · ${dec(k.avg_lift, 1)}x`}
          meaning="Mean across every rule in the set; lift above 1 beats chance."
        />
      </section>

      {/* ------------------------------------------------ does it work? -- */}
      <section className="mt-4 grid gap-4 lg:grid-cols-3">
        <Panel
          className="lg:col-span-2"
          title="Does it beat simply showing best-sellers?"
          description="One product is hidden from each hold-out invoice and the engine recommends from the rest. The bar is the share of invoices where the hidden product came back in the top 5 — the honest test, because these invoices were never mined."
        >
          <div className="grid gap-5 sm:grid-cols-2">
            <CategoryBars
              layout="horizontal"
              height={210}
              data={[
                {
                  name: 'Association rules',
                  value: Number(((k.hit_rate_at_k || 0) * 100).toFixed(2)),
                  best: true,
                },
                {
                  name: 'Popularity baseline',
                  value: Number(((k.popularity_baseline_hit_rate || 0) * 100).toFixed(2)),
                },
              ]}
              valueKey="value"
              highlightKey="best"
              valueFormat={(v) => `${v}%`}
            />
            <div className="flex flex-col justify-center gap-4">
              <div>
                <p className="num text-3xl font-semibold" style={{ color: 'var(--good)' }}>
                  {dec(k.uplift_vs_popularity, 1)}x
                </p>
                <p className="mt-0.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                  better than recommending the shop's best-sellers to everyone.
                </p>
              </div>
              <Meter
                label="Basket coverage"
                value={k.basket_coverage || 0}
                tone="good"
                caption="Hold-out invoices that received at least one rule-based suggestion."
              />
            </div>
          </div>
        </Panel>

        <Panel
          title="Catalog the engine can speak for"
          description="Products without a rule fall back to best-sellers, labelled as such."
        >
          <Donut
            centreValue={pct(k.catalog_coverage, 0)}
            centreLabel="have a rule"
            slices={[
              { name: 'With association rules', value: withRules, display: int(withRules) },
              { name: 'Fallback only', value: withoutRules, display: int(withoutRules) },
            ]}
          />
          {perProduct && (
            <dl className="mt-4 grid grid-cols-3 gap-2 border-t pt-3 text-center" style={{ borderColor: 'var(--border)' }}>
              {[
                ['Median rules', int(perProduct.median)],
                ['Most rules', int(perProduct.max)],
                ['Only one rule', int(perProduct.products_with_one_rule)],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="label-xs">{label}</dt>
                  <dd className="num mt-0.5 text-base font-semibold">{value}</dd>
                </div>
              ))}
            </dl>
          )}
        </Panel>
      </section>

      {/* ------------------------------------------------- distributions -- */}
      <Panel
        className="mt-4"
        title="Rule quality distributions"
        description={`Where the ${int(k.rules)} rules sit on each metric, plus the size of the baskets they were mined from. Metric tails are clipped at the 99th percentile.`}
      >
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ['Lift', hist.lift?.bins, (v) => v.toFixed(1), 'Above 1 means better than chance'],
            ['Confidence', hist.confidence?.bins, (v) => v.toFixed(2), 'How often the pairing happens'],
            ['Support', hist.support?.bins, (v) => v.toFixed(3), 'Share of invoices containing both'],
          ].map(([label, bins, fmt, note]) => (
            <div key={label}>
              <p className="label-xs">{label}</p>
              <p className="mb-1.5 text-[11px]" style={{ color: 'var(--text-muted)' }}>{note}</p>
              <MetricHistogram bins={bins} height={180} xFormat={fmt} />
            </div>
          ))}

          {/* The API reports basket size as summary statistics rather than bins,
              so it is shown as the five-number summary it actually is instead of
              being drawn as a histogram it cannot support. */}
          <div>
            <p className="label-xs">Basket size</p>
            <p className="mb-1.5 text-[11px]" style={{ color: 'var(--text-muted)' }}>
              Distinct products per invoice
            </p>
            {hist.basket_size ? (
              <dl className="space-y-1.5">
                {[
                  ['Mean', dec(hist.basket_size.mean, 1)],
                  ['Median', dec(hist.basket_size.median, 0)],
                  ['95th percentile', dec(hist.basket_size.p95, 0)],
                  ['Largest', int(hist.basket_size.max)],
                ].map(([label, value]) => (
                  <div
                    key={label}
                    className="flex items-center justify-between rounded-lg px-2.5 py-1.5"
                    style={{ background: 'var(--surface-2)' }}
                  >
                    <dt className="text-xs" style={{ color: 'var(--text-secondary)' }}>{label}</dt>
                    <dd className="num text-sm font-semibold">{value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No data.</p>
            )}
            <p className="mt-2 text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              A median of {dec(hist.basket_size?.median, 0)} against a mean of{' '}
              {dec(hist.basket_size?.mean, 1)} shows a long tail of very large wholesale orders.
            </p>
          </div>
        </div>
        <p className="mt-3 border-t pt-3 text-xs leading-relaxed" style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
          All three metric distributions are heavily right-skewed, which is what a healthy rule set
          looks like: the mining thresholds cut the weak left tail away, and the thin right tail is
          the small number of genuinely strong pairings worth acting on first.
        </p>
      </Panel>

      {/* --------------------------------------------------- top pairs --- */}
      <section className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel
          title="Strongest product pairings"
          description="Ranked by lift — how much more often the pair is bought together than their individual popularity predicts. Mirrored directions are collapsed to one row."
        >
          <CategoryBars
            data={topPairs}
            valueKey="lift"
            height={290}
            labelWidth={200}
            tickLines={2}
            tickChars={26}
            valueFormat={(v) => `${v}x`}
          />
        </Panel>

        <Panel
          title="Revenue simulation at a glance"
          description="Default assumptions from the hold-out window. These are modelled estimates under chosen adoption rates, not measured uplift."
          actions={<Link className="btn btn-sm" to="/simulator">Open simulator</Link>}
        >
          {scenarioBars.length ? (
            <>
              <CategoryBars
                layout="horizontal"
                data={scenarioBars}
                valueKey="revenue"
                highlightKey="base"
                height={240}
                valueFormat={(v) => money(v)}
              />
              <p className="mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
                {int(data.simulation_defaults?.assumptions?.eligible_transactions)} eligible
                transactions × adoption rate ×{' '}
                {money(data.simulation_defaults?.assumptions?.average_order_value)} average extra
                purchase.
              </p>
            </>
          ) : (
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No simulation defaults.</p>
          )}
        </Panel>
      </section>

      {/* ----------------------------------------------- top products --- */}
      <Panel
        className="mt-4"
        title="Best-selling products the engine can recommend from"
        description="The products appearing in the most invoices that also trigger at least one association rule — the anchors a cross-sell surface would sit on."
      >
        <ul className="grid gap-2 md:grid-cols-2">
          {topProducts.map((product, i) => (
            <li
              key={product.stock_code}
              className="flex items-center gap-3 rounded-xl p-2.5"
              style={{ background: 'var(--surface-2)' }}
            >
              <span className="num w-5 shrink-0 text-center text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
                {i + 1}
              </span>
              <ProductPhoto category={product.category} size="md" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium" title={product.product_name}>
                  {product.product_name}
                </span>
                <span className="num block text-xs" style={{ color: 'var(--text-muted)' }}>
                  {product.stock_code} · {money(product.median_unit_price)}
                </span>
              </span>
              <span className="shrink-0 text-right">
                <span className="num block text-sm font-semibold">{int(product.invoice_count)}</span>
                <Sparkbar
                  value={product.invoice_count}
                  max={maxInvoices}
                  title={`${product.invoice_count} invoices`}
                />
              </span>
            </li>
          ))}
        </ul>
        <DerivedCategoryNote className="mt-3" />
      </Panel>

      {/* ---------------------------------------------------- insights --- */}
      <section className="mt-6">
        <div className="mb-3 flex items-center gap-2">
          <TrendingUp size={18} style={{ color: 'var(--accent)' }} />
          <h2 className="panel-title">What the rule set is telling you</h2>
        </div>
        {insights.loading && <div className="skeleton h-40" />}
        {insights.error && <ErrorState message={insights.error} onRetry={insights.reload} />}
        {insights.data && (
          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {insights.data.insights.map((insight) => (
              <InsightCard key={insight.id} insight={insight} />
            ))}
          </div>
        )}
      </section>

      <p className="mt-6 text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
        Association rules describe historical co-occurrence in this dataset. They are evidence for a
        merchandising decision, not a prediction that any individual customer will buy.
      </p>
    </>
  )
}
