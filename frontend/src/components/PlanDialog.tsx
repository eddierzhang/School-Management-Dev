import { useState } from 'react'
import { api, ApiError } from '../api'
import type { Recommendation } from '../types'
import { ErrorNote } from './ui'

const KINDS = [
  ['tutoring', 'Targeted tutoring'],
  ['homework-recovery', 'Homework recovery'],
  ['check-in', 'Check-in'],
  ['attendance-plan', 'Attendance plan'],
  ['family-contact', 'Family contact'],
  ['enrichment', 'Enrichment'],
] as const

/** Opening a plan turns a computed recommendation into something someone owns. */
export function PlanDialog({ sid, name, seed, onClose, onSaved }: {
  sid: string
  name: string
  seed?: Recommendation
  onClose: () => void
  onSaved: () => void
}) {
  const [kind, setKind] = useState(seed?.kind ?? 'tutoring')
  const [title, setTitle] = useState(seed?.title ?? '')
  const [rationale, setRationale] = useState(seed?.rationale ?? '')
  const [owner, setOwner] = useState(seed?.suggested_owner ?? 'Support office')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save() {
    setSaving(true)
    setError(null)
    try {
      await api.createIntervention({
        student_sid: sid, kind, title: title.trim(), rationale: rationale.trim(),
        course_code: seed?.course_code ?? null, owner,
      })
      onSaved()
      onClose()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The plan could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <button className="scrim" style={{ zIndex: 60 }} onClick={onClose} aria-label="Cancel" />
      <aside className="drawer" style={{ zIndex: 70, width: 'min(460px, 100%)' }} role="dialog" aria-modal="true" aria-labelledby="plan-title">
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id="plan-title">Open a support plan</h2>
            <div className="sub" style={{ marginTop: 3 }}>
              {name} · <span className="code">{sid}</span>
              {seed?.course_code && <> · <span className="code">{seed.course_code}</span></>}
            </div>
          </div>
          <button className="btn sm ghost" onClick={onClose}>Close</button>
        </div>
        <div className="drawer-body">
          {error && <ErrorNote error={error} />}
          <div className="field">
            <label htmlFor="plan-kind">Kind of support</label>
            <select id="plan-kind" className="inp" value={kind} onChange={(e) => setKind(e.target.value)}>
              {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="plan-title-in">What will happen</label>
            <input id="plan-title-in" className="inp" value={title} placeholder="Small-group tutoring, Tuesdays at lunch"
              onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="plan-why">Why (kept with the plan)</label>
            <textarea id="plan-why" className="inp" rows={4} value={rationale} onChange={(e) => setRationale(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="plan-owner">Who owns it</label>
            <input id="plan-owner" className="inp" value={owner} onChange={(e) => setOwner(e.target.value)} />
          </div>
          <p className="sub" style={{ margin: 0 }}>
            A student can only have one active plan of a given kind per class, so this will not
            duplicate something already running.
          </p>
        </div>
        <div className="drawer-foot">
          <button className="btn primary" disabled={saving || title.trim().length < 3} onClick={save}>
            {saving ? 'Saving…' : 'Open the plan'}
          </button>
          <button className="btn ghost" onClick={onClose}>Cancel</button>
        </div>
      </aside>
    </>
  )
}
