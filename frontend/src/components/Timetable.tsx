import { api } from '../api'
import { useApi } from '../useApi'
import type { SectionSlot, StudentPeriod } from '../types'
import { ErrorNote, Loading, Pill } from './ui'

export const periodLabel = (p: number) => (p === 0 ? 'Other' : `P${p}`)

/** One student's day, period by period. A period with two classes is a clash, shown, never hidden. */
export function Timetable({ sid, compact = false }: { sid: string; compact?: boolean }) {
  const { data, error, loading, reload } = useApi(() => api.studentSchedule(sid), [sid])
  if (loading) return <Loading what="the timetable" />
  if (error) return <ErrorNote error={error} onRetry={reload} />
  if (!data) return null

  const rows = data.periods.filter((p) => !compact || p.period > 0 || p.enrolled.length || p.waitlisted.length)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div className="sub">
        {data.classes} classes · {data.credits} credits
        {data.free_periods.length > 0 && <> · free in {data.free_periods.map(periodLabel).join(', ')}</>}
        {data.waitlisted > 0 && <> · waiting for {data.waitlisted}</>}
      </div>
      {data.clashes > 0 && (
        <div className="banner critical" style={{ margin: 0 }}>
          <span style={{ flex: 1 }}>
            <b>Enrolled in two classes at once in {data.clashes === 1 ? 'one period' : `${data.clashes} periods`}.</b>{' '}
            The registrar needs to move one of them.
          </span>
        </div>
      )}
      <div className="panelbox" style={{ overflow: 'hidden' }}>
        {rows.map((p, i) => <PeriodRow key={p.period} row={p} first={i === 0} compact={compact} />)}
      </div>
    </div>
  )
}

function PeriodRow({ row, first, compact }: { row: StudentPeriod; first: boolean; compact: boolean }) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '42px minmax(0, 1fr)', gap: 10, alignItems: 'start',
      padding: compact ? '7px 12px' : '9px 14px', borderTop: first ? 0 : '1px solid var(--rule)',
      background: row.clash ? 'var(--critical-wash)' : undefined,
    }}>
      <span className="code" style={{ color: 'var(--muted)', paddingTop: 2 }}>{periodLabel(row.period)}</span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
        {row.enrolled.length === 0 && row.waitlisted.length === 0 && <span className="sub">Free</span>}
        {row.enrolled.map((s) => <SlotLine key={s.code} s={s} />)}
        {row.clash && <span><Pill kind="critical">Two classes at once</Pill></span>}
        {row.waitlisted.map((s) => (
          <span key={s.code} className="sub">
            Waitlisted for {s.title} <span className="code">{s.code}</span> · {s.room}
          </span>
        ))}
      </div>
    </div>
  )
}

function SlotLine({ s }: { s: SectionSlot }) {
  return (
    <div style={{ minWidth: 0 }}>
      <b style={{ fontSize: 13 }}>{s.title}</b>
      <div className="sub">
        <span className="code">{s.code}</span> · {s.teacher} · {s.room}
      </div>
    </div>
  )
}
