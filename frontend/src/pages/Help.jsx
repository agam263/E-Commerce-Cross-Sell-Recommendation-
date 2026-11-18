import {
  ArrowRight,
  BookOpen,
  CircleHelp,
  Layers,
  Scale,
  TriangleAlert,
} from 'lucide-react'
import { PageHeader, Panel } from '../components/Layout'
import { ProductPhoto } from '../components/ProductTile'
import { IMAGE_CREDITS } from '../lib/categoryImages'

/* A worked example used throughout the page, so every metric is explained
   against the same concrete numbers rather than in the abstract. */
const EXAMPLE = {
  invoices: 1000,
  withA: 200,
  withB: 100,
  withBoth: 60,
}

function Formula({ children }) {
  return (
    <code
      className="block overflow-x-auto rounded-md px-2.5 py-1.5 text-xs"
      style={{ background: 'var(--surface-2)', color: 'var(--accent-text)', fontFamily: 'ui-monospace, monospace' }}
    >
      {children}
    </code>
  )
}

function MetricBlock({ name, formula, worked, meaning }) {
  return (
    <div className="rounded-xl p-3.5" style={{ background: 'var(--surface-2)' }}>
      <p className="panel-title text-sm">{name}</p>
      <div className="mt-2 space-y-1.5">
        <Formula>{formula}</Formula>
        <Formula>{worked}</Formula>
      </div>
      <p className="mt-2 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        {meaning}
      </p>
    </div>
  )
}

export default function Help() {
  const { invoices, withA, withB, withBoth } = EXAMPLE

  return (
    <>
      <PageHeader
        title="Documentation"
        description="What the numbers mean, how the system is put together, and what it cannot tell you."
      />

      {/* --------------------------------------------------- what it does -- */}
      <Panel
        className="mb-4"
        title="What this application does"
        description="It finds products that get bought together, then uses those patterns to suggest what to sell alongside whatever is already in a basket."
      >
        <div className="grid gap-3 md:grid-cols-3">
          {[
            ['Learn', 'Apriori scans a year of invoices and finds product combinations that occur often enough to be worth noticing.'],
            ['Explain', 'Each combination becomes a rule with support, confidence and lift — numbers that say how common, how reliable and how far above chance it is.'],
            ['Apply', 'Given a basket, the engine fires every rule whose "if" side is already present, ranks what is left, and shows the evidence behind each suggestion.'],
          ].map(([step, text], i) => (
            <div key={step} className="rounded-xl p-3.5" style={{ background: 'var(--surface-2)' }}>
              <span className="chip chip-accent">{i + 1}. {step}</span>
              <p className="mt-2 text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {text}
              </p>
            </div>
          ))}
        </div>
      </Panel>

      {/* ------------------------------------------------- worked example -- */}
      <Panel
        className="mb-4"
        title="The three metrics, on one worked example"
        description={`Imagine ${invoices.toLocaleString()} invoices. Product A appears in ${withA}, product B in ${withB}, and both together in ${withBoth}.`}
      >
        <div className="mb-4 flex flex-wrap items-center justify-center gap-4 rounded-xl p-4" style={{ background: 'var(--surface-2)' }}>
          <div className="flex items-center gap-2.5">
            <ProductPhoto category="Bags & Totes" size="md" />
            <div>
              <p className="text-sm font-semibold">Product A</p>
              <p className="num text-xs" style={{ color: 'var(--text-muted)' }}>{withA} invoices</p>
            </div>
          </div>
          <ArrowRight size={20} style={{ color: 'var(--accent)' }} />
          <div className="flex items-center gap-2.5">
            <ProductPhoto category="Kitchen & Dining" size="md" />
            <div>
              <p className="text-sm font-semibold">Product B</p>
              <p className="num text-xs" style={{ color: 'var(--text-muted)' }}>{withB} invoices</p>
            </div>
          </div>
          <div className="rounded-lg px-3 py-2" style={{ background: 'var(--accent-weak)' }}>
            <p className="label-xs">Bought together</p>
            <p className="num text-lg font-semibold" style={{ color: 'var(--accent-text)' }}>{withBoth}</p>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <MetricBlock
            name="Support"
            formula="support(A∪B) = invoices with both ÷ all invoices"
            worked={`= ${withBoth} ÷ ${invoices} = ${(withBoth / invoices).toFixed(3)}`}
            meaning="How common the combination is. Low support means the rule rests on few invoices, so treat it carefully however impressive confidence and lift look."
          />
          <MetricBlock
            name="Confidence"
            formula="confidence(A→B) = support(A∪B) ÷ support(A)"
            worked={`= ${withBoth} ÷ ${withA} = ${(withBoth / withA).toFixed(2)}`}
            meaning={`Of the invoices that contained A, ${((withBoth / withA) * 100).toFixed(0)}% also contained B. This is the "how often does this actually happen" number, and what the shipped ranking sorts on.`}
          />
          <MetricBlock
            name="Lift"
            formula="lift(A→B) = confidence(A→B) ÷ support(B)"
            worked={`= ${(withBoth / withA).toFixed(2)} ÷ ${(withB / invoices).toFixed(2)} = ${((withBoth / withA) / (withB / invoices)).toFixed(1)}x`}
            meaning={`B appears ${((withBoth / withA) / (withB / invoices)).toFixed(1)}x more often alongside A than its own popularity would predict. Lift of 1 means no association; below 1 the pair actually repels.`}
          />
        </div>
      </Panel>

      {/* ---------------------------------------------------------- how --- */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="How Apriori works" description="The algorithm behind the rules (Agrawal & Srikant, VLDB 1994).">
          <ol className="space-y-2.5">
            {[
              ['Count single products', 'Keep the ones appearing in at least min_support of invoices. Everything else is discarded now and never reconsidered.'],
              ['Build pairs from survivors', 'The downward-closure property: if a product is too rare on its own, any pair containing it is at least as rare. That is what makes the search tractable.'],
              ['Count and prune again', 'Pairs below the threshold are dropped. Repeat for larger sizes until nothing survives.'],
              ['Turn itemsets into rules', 'Each frequent itemset is split into an "if" side and a "then" side, and scored with support, confidence and lift.'],
              ['Filter', 'Rules below the confidence and lift floors are discarded, so only real associations are served.'],
            ].map(([title, text], i) => (
              <li key={title} className="flex gap-3">
                <span
                  className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold"
                  style={{ background: 'var(--accent-weak)', color: 'var(--accent-text)' }}
                >
                  {i + 1}
                </span>
                <span>
                  <span className="block text-sm font-semibold">{title}</span>
                  <span className="block text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                    {text}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        </Panel>

        <div className="space-y-4">
          <Panel title="How a recommendation is produced">
            <ol className="list-decimal space-y-1.5 pl-5 text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              <li>Invoice lines are cleaned: cancellations, returns, zero-price lines and service codes such as postage are excluded.</li>
              <li>Each invoice becomes a basket of distinct products — ten units still counts once.</li>
              <li>Apriori mines the training window only; the last 15% of invoices are never seen.</li>
              <li>At serving time a rule fires only when its whole "if" side is in your basket.</li>
              <li>Products already in the basket are never recommended back.</li>
              <li>Survivors are ranked and the top K are returned with their evidence.</li>
              <li>If nothing fires, best-sellers are shown — labelled as a fallback, with no invented metrics.</li>
            </ol>
          </Panel>

          <Panel title="How revenue simulation works">
            <Formula>expected_additional_orders = eligible_transactions × adoption_rate</Formula>
            <Formula>estimated_incremental_revenue = expected_additional_orders × average_order_value</Formula>
            <p className="mt-2 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              Two multiplications on assumptions you supply. The model contributes the defaults —
              eligible transactions from hold-out basket coverage, order value from the
              support-weighted mean — but adoption rate is a business judgement, not a measurement.
            </p>
          </Panel>
        </div>
      </div>

      {/* -------------------------------------------------- limitations --- */}
      <Panel
        className="mt-4"
        title="Limitations — read before acting on this"
        description="Each of these is a real constraint on what the numbers can support."
      >
        <div className="grid gap-3 md:grid-cols-2">
          {[
            ['Association, not causation', 'A rule says two products appeared together historically. It does not say promoting one causes the other to sell. Only a controlled experiment can show that.'],
            ['Simulated revenue is not measured uplift', 'The simulator multiplies your assumptions together. Establishing real uplift needs a live test.'],
            ['Popular products dominate confidence', 'A minimum lift of 2 and a minimum antecedent count of 25 stop a best-seller being recommended next to everything; confidence then orders what is left.'],
            ['Rare products have no rules', 'Products below the support threshold fall back to best-sellers, labelled as such rather than dressed up with fake metrics.'],
            ['One dataset, one year, mostly one market', 'A UK gift wholesaler, Dec 2010 – Dec 2011. Seasonality is baked into these rules.'],
            ['Categories and icons are derived', 'The dataset has no product images and no category column. Categories are parsed from product names as a reading aid — they are not the retailer’s taxonomy.'],
            ['Returns are excluded from the baseline', 'A modelling choice recorded in the cleaning audit; a returns analysis would need the excluded rows.'],
            ['Colour variants look like cross-sells', 'The highest-lift pairs are often the same product in another colour. Statistically strong, commercially a range-merchandising signal rather than a true cross-sell.'],
          ].map(([title, text]) => (
            <div key={title} className="flex gap-3 rounded-xl p-3" style={{ background: 'var(--surface-2)' }}>
              <TriangleAlert size={16} className="mt-0.5 shrink-0" style={{ color: 'var(--warn)' }} />
              <div>
                <p className="text-sm font-semibold">{title}</p>
                <p className="mt-0.5 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                  {text}
                </p>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      {/* ------------------------------------------------ image credits --- */}
      <Panel
        className="mt-4"
        title="About the product images"
        description="Where the photographs come from, and what they do and do not show."
      >
        <div
          className="mb-4 flex items-start gap-3 rounded-xl p-3.5"
          style={{
            background: 'var(--warn-weak)',
            border: '1px solid color-mix(in srgb, var(--warn) 30%, transparent)',
          }}
        >
          <TriangleAlert size={18} className="mt-0.5 shrink-0" style={{ color: 'var(--warn)' }} />
          <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            <strong style={{ color: 'var(--warn)' }}>These are not photographs of the products.</strong>{' '}
            The Online Retail dataset is invoice lines — it carries no imagery and no category
            column, and searching a photo library for the real product names
            (&ldquo;WHITE HANGING HEART T-LIGHT HOLDER&rdquo;, &ldquo;JUMBO BAG RED
            RETROSPOT&rdquo;) returns nothing at all. Each product therefore shows one
            photograph chosen to represent its derived <em>category</em>. Products we could not
            categorise show a neutral icon rather than a picture implying we know what they are.
          </p>
        </div>

        <ul className="grid gap-2 sm:grid-cols-2">
          {IMAGE_CREDITS.map((credit) => (
            <li
              key={credit.category}
              className="flex items-center gap-3 rounded-lg p-2.5"
              style={{ background: 'var(--surface-2)' }}
            >
              <ProductPhoto category={credit.category} size="md" />
              <span className="min-w-0 text-xs leading-relaxed">
                <span className="block text-sm font-semibold">{credit.category}</span>
                <span className="block" style={{ color: 'var(--text-secondary)' }}>
                  {credit.author} ·{' '}
                  {credit.license_url ? (
                    <a className="link" href={credit.license_url} target="_blank" rel="noreferrer">
                      {credit.license}
                    </a>
                  ) : (
                    credit.license
                  )}
                </span>
                {credit.source_page && (
                  <a
                    className="link block truncate"
                    href={credit.source_page}
                    target="_blank"
                    rel="noreferrer"
                    title={credit.commons_title}
                  >
                    {credit.commons_title.replace(/^File:/, '')}
                  </a>
                )}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          All images are from Wikimedia Commons under Public Domain, CC0, CC BY or CC BY-SA
          licences; none are non-commercial. They are downloaded once by
          <code className="px-1">scripts/fetch_category_images.py</code> and served from this
          application, so opening the dashboard makes no request to any external host.
        </p>
      </Panel>

      {/* ----------------------------------------------------- glossary --- */}
      <Panel className="mt-4" title="Glossary">
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[
            ['Frequent itemset', 'A set of products that appears together in at least min_support of invoices.', Layers],
            ['Antecedent', 'The "if" side of a rule — what must already be in the basket.', CircleHelp],
            ['Consequent', 'The "then" side — the product being recommended.', ArrowRight],
            ['Leverage', 'Absolute excess co-occurrence over independence. Useful when lift is inflated by a rare consequent.', Scale],
            ['Hit rate @K', 'Hide one product from a hold-out invoice, recommend from the rest, and check whether the hidden product came back in the top K.', BookOpen],
            ['Cohort', 'Whether the invoice was a customer’s first or a repeat purchase, decided from their invoice sequence at the time — never using later information.', CircleHelp],
          ].map(([term, text, Icon]) => (
            <div key={term}>
              <dt className="flex items-center gap-1.5 text-sm font-semibold">
                <Icon size={14} style={{ color: 'var(--accent)' }} />
                {term}
              </dt>
              <dd className="mt-0.5 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {text}
              </dd>
            </div>
          ))}
        </dl>
      </Panel>
    </>
  )
}
