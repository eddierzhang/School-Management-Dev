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
