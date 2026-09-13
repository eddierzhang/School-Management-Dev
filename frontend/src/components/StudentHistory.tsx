import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api'
import { useCan } from '../auth'
import { useApi } from '../useApi'
import type { Band, StudentDetail } from '../types'
import { TrendLines } from './charts'
import { BAND_LABEL, ErrorNote, Icon, Loading } from './ui'

const day = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

/** The student's indices over the term, with plans and overrides marked where they happened. */
export function HistoryBlock({ sid, name, refresh }: { sid: string; name: string; refresh: number }) {
  const { data, error, loading, reload } = useApi(() => api.studentHistory(sid), [sid, refresh])
  return (
    <div className="block">
      <h3>Over the term</h3>
      {loading && !data && <Loading what="history" />}
      {error && <ErrorNote error={error} onRetry={reload} />}
      {data && (
        <TrendLines
          ariaLabel={`Struggle and excelling index for ${name}, by week`}
          points={data.snapshots.map((s) => ({ on: s.on, struggle: s.struggle_index, excel: s.excel_index }))}
          events={data.events.filter((e) => e.kind !== 'plan-completed' && e.kind !== 'plan-declined')}
          bands={[{ at: 55, label: 'needs a plan' }, { at: 35, label: 'watch' }]}
        />
      )}
    </div>
  )
}

/** Shows an active override, and lets plan owners overrule the index with a reason and an end date. */
export function OverrideBlock({ student, onChanged }: { student: StudentDetail; onChanged: () => void }) {
  const canOverride = useCan('plans.write')
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const o = student.override
  const flagged = student.computed_band === 'needs-plan' || student.computed_band === 'watch'

  async function revoke() {
    if (!o) return
    setError(null)
    try { await api.revokeOverride(student.sid, o.id); onChanged() } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The override was not removed.')
    }
  }

  if (!o && !canOverride) return null
  return (
    <div className="block">
      {error && <ErrorNote error={error} />}
      {o ? (
        <div className="override-note" role="note">
          <Icon name="warning" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <b>
              {o.kind === 'acknowledge'
                ? 'Marked as known and in hand'
                : `Band set to ${BAND_LABEL[o.band as Band]} — the index says ${BAND_LABEL[student.computed_band]}`}
            </b>
            <div className="sub" style={{ color: 'var(--ink-2)' }}>“{o.note}”</div>
            <div className="sub">{o.created_by} · until {day(o.expires_on)}</div>
          </div>
          {canOverride && <button className="btn sm ghost" onClick={() => void revoke()}>Remove</button>}
        </div>
      ) : open ? (
        <OverrideForm student={student} flagged={flagged} onDone={() => { setOpen(false); onChanged() }} onCancel={() => setOpen(false)} />
      ) : (
        <div>
          <button className="btn sm ghost" onClick={() => setOpen(true)}>Overrule the index…</button>
        </div>
      )}
    </div>
  )
}

function OverrideForm({ student, flagged, onDone, onCancel }: {
  student: StudentDetail; flagged: boolean; onDone: () => void; onCancel: () => void
}) {
  const inTwoWeeks = new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10)
  const [kind, setKind] = useState<'acknowledge' | 'set-band'>(flagged ? 'acknowledge' : 'set-band')
  const [band, setBand] = useState<Band>(student.computed_band === 'steady' ? 'watch' : 'steady')
  const [note, setNote] = useState('')
  const [until, setUntil] = useState(inTwoWeeks)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await api.createOverride(student.sid, { kind, band: kind === 'set-band' ? band : null, note, expires_on: until })
      onDone()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'The override was not saved.')
    } finally { setBusy(false) }
  }

  return (
    <form className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 9 }} onSubmit={submit}>
      <b style={{ fontSize: 13 }}>Overrule the index for {student.name.split(' ')[0]}</b>
      <p className="sub" style={{ margin: 0 }}>
        The index keeps being computed and shown beside your decision. Overrides end on the date you
        set, so they get looked at again, and they are recorded in the audit log.
      </p>
      {error && <ErrorNote error={error} />}
      <div className="field">
        <label htmlFor="ov-kind">What to record</label>
        <select id="ov-kind" className="inp" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
          {flagged && <option value="acknowledge">The concern is known and in hand</option>}
          <option value="set-band">The index is wrong about this student</option>
        </select>
      </div>
      {kind === 'set-band' && (
        <div className="field">
          <label htmlFor="ov-band">Band that fits</label>
          <select id="ov-band" className="inp" value={band} onChange={(e) => setBand(e.target.value as Band)}>
            {(Object.keys(BAND_LABEL) as Band[]).filter((b) => b !== student.computed_band)
              .map((b) => <option key={b} value={b}>{BAND_LABEL[b]}</option>)}
          </select>
        </div>
      )}
      <div className="field">
        <label htmlFor="ov-note">Why</label>
        <textarea id="ov-note" className="inp" rows={2} required minLength={10} value={note}
          placeholder="e.g. grades are from a unit retaken last week; family meeting held on the 10th"
          onChange={(e) => setNote(e.target.value)} />
      </div>
      <div className="field" style={{ maxWidth: 200 }}>
        <label htmlFor="ov-until">Until (at most 90 days)</label>
        <input id="ov-until" className="inp" type="date" required value={until} onChange={(e) => setUntil(e.target.value)} />
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn sm primary" type="submit" disabled={busy || note.trim().length < 10}>Save override</button>
        <button className="btn sm ghost" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}
