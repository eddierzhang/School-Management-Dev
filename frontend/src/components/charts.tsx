import { useCallback, useState } from 'react'
import type { ReactNode } from 'react'
import { statusColor } from './ui'
import type { StatusKind } from '../types'

/* Charts follow one scale, thin marks, hairline grid, selective direct labels,
   and every one has a table twin in the view that hosts it. */

interface TipState { x: number; y: number; content: ReactNode }

export function useTooltip() {
  const [tip, setTip] = useState<TipState | null>(null)
  const show = useCallback((e: { clientX: number; clientY: number }, content: ReactNode) => {
    setTip({ x: e.clientX, y: e.clientY, content })
  }, [])
  const hide = useCallback(() => setTip(null), [])
  const node = tip ? (
    <div
      role="status"
      style={{
        position: 'fixed', zIndex: 60, pointerEvents: 'none',
        left: Math.min(tip.x + 14, window.innerWidth - 260),
        top: Math.min(tip.y + 14, window.innerHeight - 130),
        background: 'var(--card)', border: '1px solid var(--rule-strong)', borderRadius: 7,
        padding: '9px 11px', boxShadow: 'var(--shadow-2)', fontSize: 12, maxWidth: 250,
      }}
    >
      {tip.content}
    </div>
  ) : null
  return { show, hide, node }
}

export function TipRows({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <>
      <div style={{ fontWeight: 700, marginBottom: 5 }}>{title}</div>
      <dl style={{ display: 'grid', gridTemplateColumns: 'auto auto', gap: '2px 12px', margin: 0 }}>
        {rows.map(([k, v]) => (
          <div key={k} style={{ display: 'contents' }}>
            <dt style={{ color: 'var(--ink-2)' }}>{k}</dt>
            <dd style={{ margin: 0, textAlign: 'right', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{v}</dd>
          </div>
        ))}
      </dl>
    </>
  )
}

/** Rounded data-end, square at the baseline. */
function barPath(x0: number, y: number, x1: number, h: number, r = 4) {
  const w = x1 - x0
  if (w <= r + 1) return null
  return `M${x0} ${y}H${x1 - r}a${r} ${r} 0 0 1 ${r} ${r}V${y + h - r}a${r} ${r} 0 0 1 ${-r} ${r}H${x0}Z`
}

export interface RankedBar {
  key: string
  label: string
  value: number
  status: StatusKind
  tip: ReactNode
  onSelect?: () => void
}

/** Horizontal ranked bars on a 0-100 scale. */
export function RankedBars({ rows, labelWidth = 190, ariaLabel, maxWidth = 900 }: {
  rows: RankedBar[]; labelWidth?: number; ariaLabel: string; maxWidth?: number
}) {
  const { show, hide, node } = useTooltip()
  const W = 720, padR = 54, padT = 26, padB = 6, rowH = 27, barH = 15
  const H = padT + rows.length * rowH + padB
  const x = (v: number) => labelWidth + (v / 100) * (W - labelWidth - padR)
  if (!rows.length) return <p className="sub">Nothing to plot.</p>

  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ minWidth: 560, maxWidth, display: 'block' }} role="img" aria-label={ariaLabel}>
        {[0, 25, 50, 75, 100].map((t) => (
          <g key={t}>
            <line className="gridline" x1={x(t)} y1={padT - 6} x2={x(t)} y2={H - padB} />
            <text x={x(t)} y={padT - 12} fontSize="10" textAnchor="middle">{t}</text>
          </g>
        ))}
        <line className="axisline" x1={labelWidth} y1={padT - 6} x2={labelWidth} y2={H - padB} />
        {rows.map((r, i) => {
          const y = padT + i * rowH
          const top = y + (rowH - barH) / 2
          const x1 = x(r.value)
          const d = barPath(labelWidth, top, x1, barH)
          const label = r.label.length > 34 ? r.label.slice(0, 33) + '…' : r.label
          return (
            <g key={r.key}>
              <text className="cat" x={labelWidth - 10} y={y + rowH / 2} fontSize="11.5" textAnchor="end" dominantBaseline="middle">{label}</text>
              {d ? <path d={d} fill={statusColor(r.status)} /> : (
                <rect x={labelWidth} y={top} width={Math.max(1, x1 - labelWidth)} height={barH} fill={statusColor(r.status)} />
              )}
              <text className="val" x={x1 + 7} y={y + rowH / 2} fontSize="11.5" dominantBaseline="middle">{Math.round(r.value)}</text>
              <rect
                className="hit" x={0} y={y} width={W} height={rowH}
                tabIndex={r.onSelect ? 0 : -1}
                role={r.onSelect ? 'button' : undefined}
                aria-label={`${r.label}, ${Math.round(r.value)}`}
                onMouseMove={(e) => show(e, r.tip)}
                onMouseLeave={hide}
                onFocus={(e) => {
                  const b = (e.target as SVGRectElement).getBoundingClientRect()
                  show({ clientX: b.left + 200, clientY: b.bottom }, r.tip)
                }}
                onBlur={hide}
                onClick={r.onSelect}
                onKeyDown={(e) => { if (r.onSelect && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); r.onSelect() } }}
              />
            </g>
          )
        })}
      </svg>
      {node}
    </>
  )
}

export interface TrendPoint { on: string; struggle: number; excel: number }
export interface TrendEvent { on: string; label: string }

const SERIES = [
  { key: 'struggle' as const, label: 'Struggle', color: 'var(--series-struggle)' },
  { key: 'excel' as const, label: 'Excelling', color: 'var(--series-excel)' },
]

const shortDay = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

/** Two indices over time on one 0–100 scale, with dated events marked along the bottom.
    Hover anywhere for a crosshair and the nearest reading. */
export function TrendLines({ points, events = [], ariaLabel, bands }: {
  points: TrendPoint[]; events?: TrendEvent[]; ariaLabel: string
  bands?: { at: number; label: string }[]
}) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 460, H = 200, padL = 30, padR = 74, padT = 12, padB = 40
  if (points.length < 2) return <p className="sub" style={{ margin: 0 }}>Not enough readings yet to show a trend.</p>

  const t = (iso: string) => new Date(iso + 'T00:00:00').getTime()
  const first = points[0]!, last = points[points.length - 1]!
  const t0 = t(first.on), t1 = t(last.on)
  const x = (iso: string) => padL + ((t(iso) - t0) / Math.max(1, t1 - t0)) * (W - padL - padR)
  const y = (v: number) => padT + (1 - v / 100) * (H - padT - padB)
  const shown = events.filter((e) => t(e.on) >= t0 && t(e.on) <= t1)
  // Direct labels at the line ends, nudged apart when the two values are close.
  const ends = SERIES.map((s) => ({ ...s, y: y(last[s.key]) }))
  const [ea, eb] = [ends[0]!, ends[1]!]
  if (Math.abs(ea.y - eb.y) < 13) {
    const mid = (ea.y + eb.y) / 2
    const [hi, lo] = ea.y <= eb.y ? [ea, eb] : [eb, ea]
    hi.y = mid - 7; lo.y = mid + 7
  }

  function nearest(clientX: number, svg: SVGSVGElement) {
    const b = svg.getBoundingClientRect()
    const px = ((clientX - b.left) / b.width) * W
    let best = 0
    points.forEach((p, i) => { if (Math.abs(x(p.on) - px) < Math.abs(x(points[best]!.on) - px)) best = i })
    setHover(best)
  }
  const h = hover !== null ? points[hover] ?? null : null

  return (
    <div style={{ position: 'relative' }}>
      <div style={{ display: 'flex', gap: 14, fontSize: 11.5, color: 'var(--ink-2)', marginBottom: 4 }} aria-hidden="true">
        {SERIES.map((s) => (
          <span key={s.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <svg width="14" height="4"><rect width="14" height="2" y="1" rx="1" fill={s.color} /></svg>{s.label} index
          </span>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', maxWidth: W }} role="img" aria-label={ariaLabel}
        onMouseMove={(e) => nearest(e.clientX, e.currentTarget)} onMouseLeave={() => setHover(null)}>
        {[0, 50, 100].map((v) => (
          <g key={v}>
            <line className="gridline" x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} />
            <text x={padL - 7} y={y(v)} fontSize="10" textAnchor="end" dominantBaseline="middle">{v}</text>
          </g>
        ))}
        {bands?.map((b) => (
          <g key={b.at}>
            <line x1={padL} x2={W - padR} y1={y(b.at)} y2={y(b.at)} stroke="var(--axis)" strokeDasharray="3 3" />
            <text x={padL + 3} y={y(b.at) - 4} fontSize="9.5">{b.label}</text>
          </g>
        ))}
        <line className="axisline" x1={padL} x2={W - padR} y1={y(0)} y2={y(0)} />
        {SERIES.map((s) => (
          <g key={s.key}>
            <polyline fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"
              points={points.map((p) => `${x(p.on)},${y(p[s.key])}`).join(' ')} />
            <circle cx={x(last.on)} cy={y(last[s.key])} r="4" fill={s.color} stroke="var(--card)" strokeWidth="2" />
          </g>
        ))}
        {ends.map((s) => (
          <text key={s.key} className="val" x={W - padR + 8} y={s.y} fontSize="11" dominantBaseline="middle">
            {s.label} {last[s.key]}
          </text>
        ))}
        <text x={padL} y={H - padB + 14} fontSize="10">{shortDay(first.on)}</text>
        <text x={W - padR} y={H - padB + 14} fontSize="10" textAnchor="end">{shortDay(last.on)}</text>
        {shown.map((e, i) => (
          <g key={`${e.on}-${i}`}>
            <line x1={x(e.on)} x2={x(e.on)} y1={padT} y2={y(0)} stroke="var(--ink-2)" strokeOpacity=".35" strokeDasharray="2 3" />
            <path d={`M${x(e.on)} ${H - padB + 20}l4.5 7h-9Z`} fill="var(--ink-2)"><title>{`${shortDay(e.on)}: ${e.label}`}</title></path>
          </g>
        ))}
        {h && (
          <g pointerEvents="none">
            <line x1={x(h.on)} x2={x(h.on)} y1={padT} y2={y(0)} stroke="var(--ink-2)" strokeWidth="1" />
            {SERIES.map((s) => <circle key={s.key} cx={x(h.on)} cy={y(h[s.key])} r="4" fill={s.color} stroke="var(--card)" strokeWidth="2" />)}
          </g>
        )}
      </svg>
      {h && (
        <div role="status" style={{
          position: 'absolute', top: 22, left: `${Math.min(62, (x(h.on) / W) * 100)}%`, pointerEvents: 'none',
          background: 'var(--card)', border: '1px solid var(--rule-strong)', borderRadius: 7, padding: '7px 10px',
          boxShadow: 'var(--shadow-2)', fontSize: 12, minWidth: 150,
        }}>
          <TipRows title={shortDay(h.on)} rows={[
            ['Struggle index', String(h.struggle)], ['Excelling index', String(h.excel)],
            ...shown.filter((e) => e.on === h.on).map((e) => ['Event', e.label] as [string, string]),
          ]} />
        </div>
      )}
      {shown.length > 0 && <div className="sub" style={{ marginTop: 2 }}>▲ marks a plan or override on that date. Hover a marker for what it was.</div>}
      <table className="tbl visually-hidden">
        <caption>{ariaLabel}</caption>
        <thead><tr><th>Date</th><th>Struggle index</th><th>Excelling index</th></tr></thead>
        <tbody>{points.map((p) => <tr key={p.on}><td>{p.on}</td><td>{p.struggle}</td><td>{p.excel}</td></tr>)}</tbody>
      </table>
    </div>
  )
}

/** Vertical columns for a distribution. */
export function Columns({ rows, ariaLabel, highlight }: {
  rows: { label: string; count: number }[]; ariaLabel: string; highlight?: (label: string) => StatusKind
}) {
  const { show, hide, node } = useTooltip()
  const W = 520, H = 186, padL = 34, padR = 12, padT = 16, padB = 30
  const max = Math.max(4, Math.ceil(Math.max(...rows.map((r) => r.count), 0) / 4) * 4)
  const band = (W - padL - padR) / Math.max(1, rows.length)
  const barW = Math.min(24, band - 14)
  const y = (v: number) => padT + (1 - v / max) * (H - padT - padB)
  const total = rows.reduce((a, r) => a + r.count, 0)

  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ minWidth: 380, display: 'block' }} role="img" aria-label={ariaLabel}>
        {[0, max / 2, max].map((t) => (
          <g key={t}>
            <line className="gridline" x1={padL} y1={y(t)} x2={W - padR} y2={y(t)} />
            <text x={padL - 8} y={y(t)} fontSize="10" textAnchor="end" dominantBaseline="middle">{t}</text>
          </g>
        ))}
        {rows.map((r, i) => {
          const cx = padL + band * i + band / 2
          const h = Math.max(0, y(0) - y(r.count))
          const status = highlight?.(r.label) ?? 'accent'
          return (
            <g key={r.label}>
              {h > 0 && <rect x={cx - barW / 2} y={y(r.count)} width={barW} height={h} rx={4} fill={statusColor(status)} />}
              {r.count > 0 && <text className="val" x={cx} y={y(r.count) - 6} fontSize="11" textAnchor="middle">{r.count}</text>}
              <text x={cx} y={H - padB + 15} fontSize="10" textAnchor="middle">{r.label}</text>
              <rect className="hit" x={cx - band / 2} y={padT} width={band} height={H - padT - padB}
                onMouseMove={(e) => show(e, <TipRows title={r.label} rows={[['Students', String(r.count)], ['Share', total ? `${Math.round((100 * r.count) / total)}%` : '—']]} />)}
                onMouseLeave={hide} />
            </g>
          )
        })}
        <line className="axisline" x1={padL} y1={y(0)} x2={W - padR} y2={y(0)} />
      </svg>
      {node}
    </>
  )
}
