/**
 * Radial association graph: the selected basket at the centre, each
 * recommended product on a spoke.
 *
 * Hand-rolled SVG rather than a graph library. The layout here is fully
 * determined -- one ring, fixed angular spacing -- so a force simulation would
 * add a dependency and non-determinism for no gain, and a deterministic layout
 * means the picture does not change between renders of the same data.
 *
 * Encoding:
 *   edge thickness  lift (how far above chance the pairing is)
 *   edge label      confidence (how often it actually happens)
 *   node size       fixed; node identity is carried by the category icon
 *
 * Thickness is a secondary encoding of a number that is also printed, so a
 * reader never has to judge magnitude by eye alone.
 */
import { useMemo, useState } from 'react'
import { categoryStyle } from '../lib/categories'
import { EmptyState } from './States'
import { Share2 } from 'lucide-react'

// The box is wider than it is tall because the spoke labels extend sideways:
// at 440 square the left- and right-hand product names were clipped by the
// viewBox edge.
const WIDTH = 720
const HEIGHT = 460
const CX = WIDTH / 2
const CY = HEIGHT / 2
const RADIUS = 150
const LABEL_CHARS = 22

function scaleWidth(lift, maxLift) {
  if (!Number.isFinite(lift) || maxLift <= 0) return 1.5
  const t = Math.min(1, Math.sqrt(lift / maxLift))
  return 1.5 + t * 5
}

export function AssociationGraph({ centreLabel, centreCategory, edges = [], onSelect = null }) {
  const [hovered, setHovered] = useState(null)

  const nodes = useMemo(() => {
    const maxLift = Math.max(...edges.map((e) => Number(e.lift) || 0), 1)
    const count = edges.length
    return edges.map((edge, i) => {
      // Start at the top and go clockwise so the first (best) item is at 12 o'clock.
      const angle = (-Math.PI / 2) + (i * 2 * Math.PI) / Math.max(count, 1)
      return {
        ...edge,
        x: CX + RADIUS * Math.cos(angle),
        y: CY + RADIUS * Math.sin(angle),
        width: scaleWidth(Number(edge.lift), maxLift),
        angle,
      }
    })
  }, [edges])

  if (!edges.length) {
    return (
      <EmptyState
        compact
        icon={Share2}
        title="No associations to draw"
        hint="Pick a product that has at least one association rule to see its network."
      />
    )
  }

  const centreStyle = categoryStyle(centreCategory)

  return (
    <div className="w-full min-w-0 overflow-x-auto">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="mx-auto block h-auto w-full"
        style={{ maxWidth: WIDTH }}
        role="img"
        aria-label={`Association graph for ${centreLabel}: ${edges.length} related products`}
      >
        {/* edges first so nodes sit on top */}
        {nodes.map((node) => {
          const active = hovered === node.stock_code
          return (
            <g key={`edge-${node.stock_code}`}>
              <line
                x1={CX}
                y1={CY}
                x2={node.x}
                y2={node.y}
                stroke={active ? 'var(--accent)' : 'var(--border-strong)'}
                strokeWidth={node.width}
                strokeLinecap="round"
                opacity={hovered && !active ? 0.3 : 1}
              />
              <text
                x={CX + (node.x - CX) * 0.55}
                y={CY + (node.y - CY) * 0.55}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize="10"
                fontWeight="650"
                fill={active ? 'var(--accent)' : 'var(--text-muted)'}
                style={{ paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 4 }}
              >
                {Number.isFinite(Number(node.confidence))
                  ? `${(Number(node.confidence) * 100).toFixed(0)}%`
                  : ''}
              </text>
            </g>
          )
        })}

        {/* spoke nodes */}
        {nodes.map((node) => {
          const style = categoryStyle(node.category)
          const active = hovered === node.stock_code
          // Labels flip side depending on which half of the circle they sit in.
          const right = node.x >= CX
          return (
            <g
              key={`node-${node.stock_code}`}
              transform={`translate(${node.x} ${node.y})`}
              onMouseEnter={() => setHovered(node.stock_code)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onSelect?.(node.stock_code)}
              style={{ cursor: onSelect ? 'pointer' : 'default' }}
            >
              <circle
                r={active ? 21 : 18}
                fill="var(--surface)"
                stroke={active ? 'var(--accent)' : style.hue}
                strokeWidth={active ? 2.5 : 1.5}
              />
              <circle r={active ? 15 : 13} fill={style.wash} />
              <text
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize="9"
                fontWeight="700"
                fill={style.hue}
              >
                {String(node.stock_code).slice(0, 5)}
              </text>
              <text
                x={right ? 26 : -26}
                y={4}
                textAnchor={right ? 'start' : 'end'}
                fontSize="10.5"
                fill="var(--text-secondary)"
                style={{ paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}
              >
                {String(node.product_name || '').length > LABEL_CHARS
                  ? `${String(node.product_name).slice(0, LABEL_CHARS - 1)}…`
                  : node.product_name}
              </text>
            </g>
          )
        })}

        {/* centre */}
        <circle r={40} cx={CX} cy={CY} fill={centreStyle.wash} stroke={centreStyle.hue} strokeWidth="2" />
        <text
          x={CX}
          y={CY - 4}
          textAnchor="middle"
          fontSize="10"
          fontWeight="700"
          fill={centreStyle.hue}
        >
          BASKET
        </text>
        <text x={CX} y={CY + 10} textAnchor="middle" fontSize="9" fill="var(--text-secondary)">
          {String(centreLabel || '').slice(0, 12)}
        </text>
      </svg>

      <p className="mt-1 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
        Line thickness is lift; the figure on each line is confidence.
        {onSelect ? ' Click a product to explore it.' : ''}
      </p>
    </div>
  )
}
