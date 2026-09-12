import type { ReactNode } from 'react'
import type { Band, StatusKind } from '../types'

/* --- status vocabulary ---------------------------------------------------
   Band -> colour is fixed here so the same student never changes colour
   between views. Status colour always travels with a label or an icon. */
export const BAND_STATUS: Record<Band, StatusKind> = {
  'needs-plan': 'critical',
  watch: 'serious',
  excelling: 'good',
  steady: 'neutral',
}
export const BAND_LABEL: Record<Band, string> = {
  'needs-plan': 'Needs a plan',
  watch: 'Watch',
  excelling: 'Excelling',
  steady: 'Steady',
}

/** Grade -> status. The cut points match the backend's policy thresholds. */
export function gradeStatus(pct: number): StatusKind {
  if (pct >= 90) return 'good'
  if (pct >= 80) return 'accent'
  if (pct >= 72) return 'warning'
  if (pct >= 65) return 'serious'
  return 'critical'
}
export const statusColor = (k: StatusKind) =>
  k === 'critical' ? 'var(--critical)'
  : k === 'serious' ? 'var(--serious)'
  : k === 'warning' ? 'var(--warning)'
  : k === 'good' ? 'var(--good)'
  : k === 'neutral' ? 'var(--rule-strong)'
  : 'var(--accent)'

export const pctText = (n: number) => `${Math.round(n)}%`
export const signed = (n: number) => (n > 0 ? `+${n.toFixed(0)}` : n.toFixed(0))

export function Icon({ name }: { name: StatusKind | 'rising' | 'falling' }) {
  const common = { width: 11, height: 11, viewBox: '0 0 12 12', 'aria-hidden': true } as const
  switch (name) {
    case 'good':
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="5" fill="none" stroke="var(--good)" strokeWidth="1.6" />
          <path d="M3.6 6.2 5.2 7.8 8.5 4.4" fill="none" stroke="var(--good)" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      )
    case 'warning':
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="5" fill="var(--warning)" />
          <path d="M6 3.3v3.2" stroke="#231a05" strokeWidth="1.6" strokeLinecap="round" />
          <circle cx="6" cy="8.7" r=".9" fill="#231a05" />
        </svg>
      )
    case 'serious':
      return (
        <svg {...common}>
          <path d="M6 1.2 11 10.4H1L6 1.2Z" fill="var(--serious)" />
          <path d="M6 4.6v2.5" stroke="#2b1108" strokeWidth="1.5" strokeLinecap="round" />
          <circle cx="6" cy="8.8" r=".85" fill="#2b1108" />
        </svg>
      )
    case 'critical':
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="5" fill="var(--critical)" />
          <path d="M4.2 4.2l3.6 3.6M7.8 4.2 4.2 7.8" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      )
    case 'rising':
    case 'falling':
      return (
        <svg {...common} style={name === 'falling' ? { transform: 'scaleY(-1)' } : undefined}>
          <path d="M1.5 9.5 4.5 5.8l2.2 2 3.8-5.1" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M7.7 2.7h2.8v2.8" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    default:
      return null
  }
}

export function Pill({ kind, children }: { kind: StatusKind; children: ReactNode }) {
  return (
    <span className={`pill ${kind}`}>
      <Icon name={kind} />
      {children}
    </span>
  )
}

export function BandPill({ band }: { band: Band }) {
  return <Pill kind={BAND_STATUS[band]}>{BAND_LABEL[band]}</Pill>
}

/** Meter fill carries severity; the track is a light step of the same hue. */
export function Meter({ value, kind, tick, label }: {
  value: number; kind: StatusKind; tick?: number; label?: string
}) {
  const clamped = Math.max(0, Math.min(100, value))
  return (
    <span className="meter-row">
      <span className="meter" style={{ ['--meter' as string]: statusColor(kind) }}>
        <i style={{ width: `${clamped}%` }} />
        {tick !== undefined && <u style={{ left: `${Math.max(0, Math.min(100, tick))}%` }} />}
      </span>
      {label && <span className="meter-lab">{label}</span>}
    </span>
  )
}

export function Stat({ k, v, c }: { k: string; v: ReactNode; c?: ReactNode }) {
  return (
    <div className="stat">
      <span className="stat-k">{k}</span>
      <span className="stat-v">{v}</span>
      {c && <span className="stat-c">{c}</span>}
    </div>
  )
}

export function Loading({ what }: { what: string }) {
  return (
    <div className="empty">
      <h2>Loading {what}…</h2>
    </div>
  )
}

export function ErrorNote({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="banner critical">
      <Icon name="critical" />
      <span style={{ flex: 1, minWidth: 200 }}>{error}</span>
      {onRetry && (
        <button className="btn sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function Delta({ value }: { value: number }) {
  if (Math.abs(value) < 1) return <span className="sub">level</span>
  const falling = value < 0
  return (
    <span style={{ color: falling ? 'var(--critical)' : 'var(--accent-ink)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <Icon name={falling ? 'falling' : 'rising'} />
      {signed(value)}
    </span>
  )
}
