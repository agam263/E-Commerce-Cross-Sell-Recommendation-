/**
 * Chart primitives.
 *
 * Design rules applied here:
 *  - every chart on this dashboard shows ONE measure, so each uses a single
 *    hue (categorical slot 1) rather than a cycled palette, and needs no legend;
 *  - grid and axes are recessive, marks carry the ink;
 *  - bars have 4px rounded data-ends anchored to the baseline and a 2px gap;
 *  - hover tooltips are on by default -- an SVG chart is an interactive chart;
 *  - values are never printed on every bar; selective direct labels only.
 *
 * Mount animation is DISABLED on every series. Recharts renders an empty
 * <g> for a bar until its enter-animation produces the first frame, so an
 * animated chart is blank in any context that does not run requestAnimationFrame
 * to completion: a throttled background tab, prefers-reduced-motion, print,
 * PDF export and headless screenshots. Static bars render on first paint.
 */
import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

/**
 * Recharts applies colour through SVG *presentation attributes*
 * (<path fill="..."/>, <line stroke="..."/>). A CSS custom property is only
 * valid in a CSS property value, not in a presentation attribute: Chrome
 * resolves `fill={c.series1}` anyway, but Safari and Firefox do not and
 * fall back to the SVG default of black -- invisible against the dark surface.
 * The symptom is a dashboard where the HTML stat tiles and tables render but
 * every chart is an empty rectangle.
 *
 * So the tokens are resolved to concrete colours here, in JS, and passed to
 * Recharts as plain strings. The fallbacks mirror the light theme in
 * index.css so a chart is never invisible even if the lookup fails.
 */
const FALLBACK = {
  series1: '#4f46e5',
  series2: '#e8710a',
  series3: '#0f8a6a',
  grid: '#ecf0f5',
  surface3: '#eef1f6',
  surface: '#ffffff',
  textMuted: '#64748b',
  textSecondary: '#4a5568',
}

const TOKENS = {
  series1: '--series-1',
  series2: '--series-2',
  series3: '--series-3',
  grid: '--grid',
  surface3: '--surface-3',
  surface: '--surface',
  textMuted: '--text-muted',
  textSecondary: '--text-secondary',
}

function readChartTheme() {
  if (typeof window === 'undefined' || !document?.documentElement) return FALLBACK
  try {
    const cs = getComputedStyle(document.documentElement)
    const out = {}
    for (const [key, token] of Object.entries(TOKENS)) {
      out[key] = cs.getPropertyValue(token).trim() || FALLBACK[key]
    }
    return out
  } catch {
    return FALLBACK
  }
}

/** Re-reads the palette whenever the theme class on <html> changes. */
export function useChartTheme() {
  const [theme, setTheme] = useState(readChartTheme)
  useEffect(() => {
    const update = () => setTheme(readChartTheme())
    update()
    let observer
    try {
      observer = new MutationObserver(update)
      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['class', 'style'],
      })
    } catch {
      /* no MutationObserver: the colours just stay as first read */
    }
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
    mq?.addEventListener?.('change', update)
    return () => {
      observer?.disconnect()
      mq?.removeEventListener?.('change', update)
    }
  }, [])
  return theme
}

/** Compact counts so the y-axis gutter never has to be wide enough to clip. */
const compact = (v) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  const a = Math.abs(n)
  // Drop the decimal above 10k: "10.5k" is wider than the axis gutter, and a
  // clipped tick is worse than a rounded one.
  if (a >= 10000) return `${Math.round(n / 1000)}k`
  if (a >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k`
  return String(n)
}

const truncate = (s, n) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)

/**
 * Category tick that renders a fixed number of single-line tspans instead of
 * letting Recharts word-wrap to an unbounded height. Wrapped ticks are what
 * makes long product names collide with their neighbours.
 *
 * With `lines={2}` a label of the form "A → B" is split across two lines.
 */
function CategoryTick(props) {
  const { x, y, payload, lines = 1, chars = 30, fill = FALLBACK.textMuted } = props
  const raw = String(payload?.value ?? '')
  const parts =
    lines === 2 && raw.includes(' → ')
      ? [raw.split(' → ')[0], `→ ${raw.split(' → ').slice(1).join(' → ')}`]
      : [raw]
  const first = parts.length === 2 ? -3 : 4
  return (
    <text x={x} y={y} textAnchor="end" fontSize={11} fill={fill}>
      {parts.map((part, i) => (
        <tspan key={i} x={x} dy={i === 0 ? first : 13}>
          {truncate(part, chars)}
        </tspan>
      ))}
    </text>
  )
}

function TooltipCard({ active, payload, label, valueFormat, labelFormat }) {
  if (!active || !payload?.length) return null
  const point = payload[0]
  return (
    <div
      className="card"
      style={{ padding: '0.55rem 0.7rem', boxShadow: '0 6px 20px rgb(0 0 0 / 0.12)', maxWidth: 260 }}
    >
      <p className="text-xs font-semibold">{labelFormat ? labelFormat(label) : label}</p>
      <p className="num text-sm" style={{ color: 'var(--text-secondary)' }}>
        {valueFormat ? valueFormat(point.value) : point.value}
      </p>
    </div>
  )
}

/**
 * Histogram of a rule metric, fed by the API's binned counts.
 * `bins` is [{ start, end, count }].
 */
export function MetricHistogram({ bins = [], height = 180, xFormat = (v) => v.toFixed(2) }) {
  const c = useChartTheme()
  const axisStyle = { fontSize: 11, fill: c.textMuted }
  const data = bins.map((bin) => ({
    name: xFormat(bin.start),
    range: `${xFormat(bin.start)} – ${xFormat(bin.end)}`,
    count: bin.count,
  }))
  if (!data.length) return <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No data.</p>
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: 0 }} barCategoryGap={2}>
        <CartesianGrid vertical={false} stroke={c.grid} />
        <XAxis
          dataKey="name"
          tick={axisStyle}
          tickLine={false}
          axisLine={{ stroke: c.grid }}
          interval="preserveStartEnd"
          minTickGap={18}
        />
        <YAxis
          tick={axisStyle}
          tickLine={false}
          axisLine={false}
          width={38}
          tickFormatter={compact}
        />
        <Tooltip
          cursor={{ fill: c.surface3 }}
          content={
            <TooltipCard
              valueFormat={(v) => `${v.toLocaleString()} rules`}
              labelFormat={(l) => {
                const row = data.find((d) => d.name === l)
                return row ? row.range : l
              }}
            />
          }
        />
        <Bar
          dataKey="count"
          fill={c.series1}
          radius={[4, 4, 0, 0]}
          maxBarSize={44}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}

/**
 * Single-series categorical bars, horizontal by default (long category names
 * stay readable without rotated labels).
 *
 * `tickLines={2}` splits an "A → B" label over two lines; pair it with enough
 * height per row (~44px) or the two lines will touch the next category.
 */
export function CategoryBars({
  data = [],
  categoryKey = 'name',
  valueKey = 'value',
  height = 220,
  valueFormat = (v) => v.toLocaleString(),
  highlightKey = null,
  layout = 'vertical',
  labelWidth = 140,
  tickLines = 1,
  tickChars = 30,
}) {
  const c = useChartTheme()
  const axisStyle = { fontSize: 11, fill: c.textMuted }
  if (!data.length) return <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No data.</p>

  if (layout === 'vertical') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 56, bottom: 4, left: 4 }}
          barCategoryGap={tickLines === 2 ? 10 : 4}
        >
          <CartesianGrid horizontal={false} stroke={c.grid} />
          <XAxis type="number" tick={axisStyle} tickLine={false} axisLine={false} tickFormatter={compact} />
          <YAxis
            type="category"
            dataKey={categoryKey}
            tick={<CategoryTick lines={tickLines} chars={tickChars} fill={c.textMuted} />}
            tickLine={false}
            axisLine={false}
            width={labelWidth}
            interval={0}
          />
          <Tooltip cursor={{ fill: c.surface3 }} content={<TooltipCard valueFormat={valueFormat} />} />
          <Bar dataKey={valueKey} radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive={false}>
            {data.map((row, i) => (
              <Cell
                key={i}
                fill={row.color || (highlightKey && row[highlightKey] ? c.series2 : c.series1)}
              />
            ))}
            <LabelList
              dataKey={valueKey}
              position="right"
              formatter={valueFormat}
              style={{ fontSize: 11, fill: c.textSecondary, fontWeight: 600 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 22, right: 8, bottom: 4, left: 0 }} barCategoryGap={6}>
        <CartesianGrid vertical={false} stroke={c.grid} />
        <XAxis dataKey={categoryKey} tick={axisStyle} tickLine={false} axisLine={{ stroke: c.grid }} />
        <YAxis tick={axisStyle} tickLine={false} axisLine={false} width={42} tickFormatter={compact} />
        <Tooltip cursor={{ fill: c.surface3 }} content={<TooltipCard valueFormat={valueFormat} />} />
        <Bar dataKey={valueKey} radius={[4, 4, 0, 0]} maxBarSize={72} isAnimationActive={false}>
          {data.map((row, i) => (
            <Cell
              key={i}
              fill={row.color || (highlightKey && row[highlightKey] ? c.series2 : c.series1)}
            />
          ))}
          <LabelList
            dataKey={valueKey}
            position="top"
            formatter={valueFormat}
            style={{ fontSize: 11, fill: c.textSecondary, fontWeight: 600 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Small inline bar used inside table rows / recommendation cards. */
export function Sparkbar({ value, max, title }) {
  const width = max > 0 ? Math.max(2, Math.min(100, (value / max) * 100)) : 0
  return (
    <span
      className="inline-block h-1.5 w-16 overflow-hidden rounded-full align-middle"
      style={{ background: 'var(--surface-3)' }}
      title={title}
    >
      <span
        className="block h-full rounded-full"
        style={{ width: `${width}%`, background: 'var(--series-1)' }}
      />
    </span>
  )
}


/**
 * Two-to-three slice donut for a share-of-whole.
 *
 * Hand-drawn rather than a Recharts PieChart: the slices need a surface-coloured
 * gap between them and a value in the middle, and the arc maths is four lines.
 * Every slice is also named in the legend, so identity is never colour-alone.
 */
export function Donut({ slices = [], centreValue, centreLabel, size = 190, thickness = 26 }) {
  const c = useChartTheme()
  const palette = [c.series1, c.surface3, c.series2]
  const total = slices.reduce((sum, s) => sum + (Number(s.value) || 0), 0)

  if (!total) {
    return <p className="text-sm" style={{ color: c.textMuted }}>No data.</p>
  }

  const radius = (size - thickness) / 2
  const centre = size / 2
  const circumference = 2 * Math.PI * radius
  let offset = 0

  return (
    <div className="flex flex-wrap items-center justify-center gap-5">
      <svg width={size} height={size} role="img" aria-label={centreLabel}>
        <g transform={`rotate(-90 ${centre} ${centre})`}>
          {slices.map((slice, i) => {
            const share = (Number(slice.value) || 0) / total
            const length = share * circumference
            const dash = `${Math.max(0, length - 2)} ${circumference - Math.max(0, length - 2)}`
            const element = (
              <circle
                key={slice.name}
                cx={centre}
                cy={centre}
                r={radius}
                fill="none"
                stroke={slice.color || palette[i % palette.length]}
                strokeWidth={thickness}
                strokeDasharray={dash}
                strokeDashoffset={-offset}
              />
            )
            offset += length
            return element
          })}
        </g>
        <text
          x={centre}
          y={centre - 2}
          textAnchor="middle"
          fontSize="22"
          fontWeight="700"
          fill={c.textSecondary}
        >
          {centreValue}
        </text>
        <text x={centre} y={centre + 16} textAnchor="middle" fontSize="10" fill={c.textMuted}>
          {centreLabel}
        </text>
      </svg>

      <ul className="space-y-2 text-sm">
        {slices.map((slice, i) => (
          <li key={slice.name} className="flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: slice.color || palette[i % palette.length] }}
            />
            <span style={{ color: c.textSecondary }}>{slice.name}</span>
            <span className="num font-semibold">{slice.display ?? slice.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
