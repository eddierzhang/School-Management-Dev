import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { ErrorNote, Pill } from './ui'

/* Kept self-contained — its own types and two small fetches — so it can sit at the
   top of any page without touching the shared API client. */

interface ChildRun {
  id: number
  agent: string
  status: 'queued' | 'running' | 'done' | 'failed' | string
  prompt: string
  summary: string
  error: string | null
  proposals: { id: number; summary: string; status: string }[]
}

interface ManagerRun {
  id: number
  status: string
  prompt: string
  summary: string
  error: string | null
  duration_ms: number
  dispatched: ChildRun[]
}

interface Briefing {
  school: string
  as_of: string
  attention: string[]
  students: { total: number; needs_plan: number; open_plans: number; attendance_pct: number | null }
  finance: { available: boolean; over_budget?: number; at_risk?: number }
  fleet: { pending_proposals: number }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch('/api' + path)
  if (!res.ok) throw new ApiError(res.status, `Request failed (${res.status})`)
  return res.json() as Promise<T>
}

const EXAMPLES = [
  'Give me a briefing on the school: what needs attention first?',
  'How is the budget looking, and which lines are in trouble?',
  'Get the team working on the most urgent problems this week.',
]

const STATUS_PILL: Record<string, 'accent' | 'good' | 'critical' | 'neutral'> = {
  queued: 'neutral', running: 'accent', done: 'good', failed: 'critical',
}

function isBusy(r: ManagerRun | undefined) {
  return !!r && (r.status === 'running' || r.dispatched.some((c) => c.status === 'running' || c.status === 'queued'))
}

export function ManagerPanel({ onChanged }: { onChanged?: () => void }) {
  const [task, setTask] = useState('')
  const [runs, setRuns] = useState<ManagerRun[]>([])
  const [brief, setBrief] = useState<Briefing | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const wasBusy = useRef(false)

  const load = useCallback(async () => {
    try {
      const [r, b] = await Promise.all([get<ManagerRun[]>('/manager/runs?limit=3'), get<Briefing>('/manager/briefing')])
      setRuns(r)
      setBrief(b)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not reach the manager.')
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const latest = runs[0]
  // Keep polling while dispatched agents work, but only the manager's own run
  // blocks a new question — the queue can take many minutes.
  const busy = isBusy(latest)
  const thinking = latest?.status === 'running'
  useEffect(() => {
    if (wasBusy.current && !busy) onChanged?.()   // proposals may have landed
    wasBusy.current = busy
    if (!busy) return
    const t = window.setInterval(() => { void load() }, 4000)
    return () => window.clearInterval(t)
  }, [busy, load, onChanged])

  async function start(text: string) {
    setStarting(true); setError(null)
    try {
      await api.runAgent('manager', text.trim() || undefined)
      setTask('')
      await load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not start the manager.')
    } finally { setStarting(false) }
  }

  const attention = brief?.attention ?? []

  return (
    <section className="sec">
      <div className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 14, borderColor: 'var(--accent)' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <h2 style={{ margin: 0 }}>General manager</h2>
          <span className="sub">Ask about the school, or tell it what to get done — it puts the other agents to work.</span>
        </div>

        <div className="field">
          <label htmlFor="mgr-task" className="visually-hidden">What do you need?</label>
          <textarea id="mgr-task" className="inp" rows={2} value={task}
            placeholder="e.g. Which classes are struggling most, and what should we do about them?"
            onChange={(e) => setTask(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !starting && !thinking) { e.preventDefault(); void start(task) }
            }} />
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <button className="btn primary" disabled={starting || thinking} onClick={() => void start(task)}>
            {thinking ? 'Thinking…' : starting ? 'Starting…' : 'Ask the manager'}
          </button>
          {EXAMPLES.map((ex) => (
            <button key={ex} className="btn sm ghost" disabled={starting || thinking}
              onClick={() => { setTask(ex); void start(ex) }}>{(ex.split(':')[0] ?? ex).replace(/\?$/, '')}</button>
          ))}
        </div>
        {error && <ErrorNote error={error} />}

        {latest && (
          <div style={{ borderTop: '1px solid var(--rule)', paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <Pill kind={STATUS_PILL[latest.status] ?? 'neutral'}>{latest.status === 'running' ? 'thinking…' : latest.status}</Pill>
              <span className="sub" style={{ flex: 1, minWidth: 200 }}>“{latest.prompt}”</span>
              {latest.status !== 'running' && latest.duration_ms > 0 && (
                <span className="sub nowrap">{Math.round(latest.duration_ms / 1000)}s</span>
              )}
            </div>
            {latest.status === 'running' && (
              <p className="sub" style={{ margin: 0 }}>Reading the school's figures on the local model — usually a minute or two.</p>
            )}
            {latest.summary && (
              <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, whiteSpace: 'pre-wrap' }}>{latest.summary}</p>
            )}
            {latest.error && <ErrorNote error={latest.error} />}

            {latest.dispatched.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div className="eyebrow">Agents it put to work</div>
                <div className="people">
                  {latest.dispatched.map((c) => (
                    <div className="person" key={c.id} style={{ alignItems: 'flex-start' }}>
                      <span className="pn">
                        <b style={{ textTransform: 'capitalize' }}>{c.agent}</b>
                        <div className="sub">{c.prompt}</div>
                        {c.summary && <div style={{ fontSize: 12.5, marginTop: 4 }}>{c.summary.slice(0, 300)}</div>}
                        {c.error && <div className="sub" style={{ color: 'var(--critical)' }}>{c.error}</div>}
                        {c.proposals.length > 0 && (
                          <div className="sub" style={{ marginTop: 3 }}>
                            Proposed: {c.proposals.map((p) => p.summary).join(' · ')}
                            {c.proposals.some((p) => p.status === 'pending') && ' — waiting for your approval below'}
                          </div>
                        )}
                      </span>
                      <Pill kind={STATUS_PILL[c.status] ?? 'neutral'}>{c.status === 'queued' ? 'waiting its turn' : c.status}</Pill>
                    </div>
                  ))}
                </div>
                <p className="sub" style={{ margin: 0 }}>
                  They run one at a time and only propose changes — nothing happens until you approve it.
                </p>
              </div>
            )}
          </div>
        )}

        {attention.length > 0 && (
          <div style={{ borderTop: '1px solid var(--rule)', paddingTop: 12 }}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Needs attention now · computed, not generated</div>
            <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
              {(showAll ? attention : attention.slice(0, 4)).map((a) => <li key={a}>{a}</li>)}
            </ul>
            {attention.length > 4 && (
              <button className="btn sm ghost" style={{ marginTop: 6 }} onClick={() => setShowAll((v) => !v)}>
                {showAll ? 'Show fewer' : `Show all ${attention.length}`}
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
