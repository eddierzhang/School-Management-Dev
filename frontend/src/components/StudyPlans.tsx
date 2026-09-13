import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import { useApi } from '../useApi'
import type { StudyClassRow, StudyDraft, StudyPlan } from '../types'
import { Delta, ErrorNote, Icon, Loading, Pill, gradeStatus, pctText } from './ui'

const day = (iso: string | null) =>
  iso ? new Date(iso + (iso.length === 10 ? 'T00:00:00' : '')).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—'

/** Study plans in the student record: per class, what the assignments show and a plan to fix it. */
export function StudyPlansBlock({ sid, onChanged }: { sid: string; onChanged?: () => void }) {
  const [tick, setTick] = useState(0)
  const data = useApi(() => api.study(sid), [sid, tick])
  const fleet = useApi(() => api.runtime(), [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const reload = () => setTick((n) => n + 1)

  const running = !!data.data?.classes.some((c) => c.latest_run?.status === 'running')
  // A draft takes a minute or more on the local model; poll only while one runs.
  useEffect(() => {
    if (!running) return
    const t = window.setInterval(reload, 3000)
    return () => window.clearInterval(t)
  }, [running])

  async function act(fn: () => Promise<unknown>, done: string) {
    setBusy(true); setError(null); setMessage(null)
    try {
      await fn()
      setMessage(done)
      onChanged?.()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That did not go through.')
    } finally {
      setBusy(false)
      reload()
    }
  }

  if (data.loading && !data.data) return <div className="block"><h3>Study plans</h3><Loading what="class work" /></div>
  if (data.error) return <div className="block"><h3>Study plans</h3><ErrorNote error={data.error} onRetry={reload} /></div>
  if (!data.data) return null
  const d = data.data
  const rt = fleet.data?.runtime
  const canDraft = !!rt?.can_run_agents

  const involved = (c: StudyClassRow) => c.needs_plan || c.active_plan_id !== null || c.drafts_waiting > 0
  const shown = showAll ? d.classes : d.classes.filter(involved)
  const hidden = d.classes.length - shown.length

  return (
    <div className="block">
      <h3>Study plans</h3>
      <p className="sub" style={{ margin: 0 }}>
        What exactly this student struggles on in each class, read from every assignment, and a
        session-by-session plan the study plan agent drafts from it. Nothing takes effect until you adopt it.
      </p>
      {error && <ErrorNote error={error} />}
      {message && (
        <div className="banner" style={{ background: 'var(--accent-wash)', border: '1px solid var(--accent)' }}>
          <Icon name="good" /><span style={{ flex: 1 }}>{message}</span>
        </div>
      )}
      {rt && !canDraft && (
        <div className="sub">
          {rt.reachable ? `${rt.model} cannot call tools, so plans cannot be drafted.` : 'Ollama is not running, so plans cannot be drafted.'}
        </div>
      )}

      {shown.length === 0 && <p className="sub" style={{ margin: 0 }}>Nothing in this student’s class work calls for a study plan.</p>}
      {shown.map((c) => (
        <ClassStudy key={c.code} sid={sid} row={c} busy={busy} canDraft={canDraft}
          plan={d.plans.find((p) => p.id === c.active_plan_id)}
          drafts={d.drafts.filter((x) => x.payload.course_code === c.code)}
          act={act} />
      ))}
      {hidden > 0 && (
        <button className="btn sm ghost" style={{ alignSelf: 'flex-start' }} onClick={() => setShowAll(true)}>
          Show {hidden} other class{hidden === 1 ? '' : 'es'} that look fine
        </button>
      )}

      {d.plans.some((p) => p.status !== 'active') && (
        <details>
          <summary className="sub" style={{ cursor: 'pointer' }}>Earlier study plans</summary>
          {d.plans.filter((p) => p.status !== 'active').map((p) => (
            <div key={p.id} style={{ marginTop: 6, fontSize: 12.5 }}>
              <span className="code">{p.course_code}</span> <b>{p.title}</b>{' '}
              <span className="sub">{p.status} {day(p.closed_on)}{p.outcome ? ` · ${p.outcome}` : ''}</span>
            </div>
          ))}
        </details>
      )}
    </div>
  )
}

function ClassStudy({ sid, row, plan, drafts, busy, canDraft, act }: {
  sid: string; row: StudyClassRow; plan?: StudyPlan; drafts: StudyDraft[]; busy: boolean; canDraft: boolean
  act: (fn: () => Promise<unknown>, done: string) => void
}) {
  const { can } = useAuth()
  const [note, setNote] = useState('')
  const [showWork, setShowWork] = useState(false)
  const last = row.latest_run
  const running = last?.status === 'running'

  return (
    <div className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <span className="code">{row.code}</span>
        <b style={{ fontSize: 13.5 }}>{row.title}</b>
        <span className="spacer" />
        <Pill kind={gradeStatus(row.pct)}>{pctText(row.pct)}</Pill>
        {row.class_pct !== null && <span className="sub">class {pctText(row.class_pct)}</span>}
      </div>

      {row.findings.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {row.findings.map((f) => (
            <div key={f} className="reason"><Icon name="warning" /><span>{f}</span></div>
          ))}
        </div>
      )}

      <div>
        <button className="btn sm ghost" onClick={() => setShowWork((v) => !v)} aria-expanded={showWork}>
          {showWork ? 'Hide assignments' : 'See every assignment'}
        </button>
      </div>
      {showWork && <Assignments sid={sid} code={row.code} />}

      {plan && <ActivePlan plan={plan} busy={busy}
        onClose={(status, outcome) => act(() => api.closeStudyPlan(plan.id, status, outcome),
          status === 'completed' ? 'Study plan marked complete.' : 'Study plan retired.')} />}

      {!plan && drafts.map((draft) => (
        <div key={draft.id} style={{ display: 'flex', flexDirection: 'column', gap: 8, borderTop: '1px solid var(--rule)', paddingTop: 9 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
            <Pill kind="accent">Draft</Pill>
            <b style={{ fontSize: 13.5 }}>{draft.payload.title}</b>
          </div>
          <PlanBody diagnosis={draft.payload.diagnosis} strands={draft.payload.focus_strands}
            sessions={draft.payload.sessions} goal={draft.payload.goal}
            catchUp={draft.payload.catch_up_assignments.length} />
          <div className="sub">
            Drafted by the study plan agent{draft.run_id !== null && <> · run #{draft.run_id}, <a href="#/agents">transcript</a></>}.
            Every figure and count it cites was checked against this student’s work.
          </div>
          {can('plans.write') ? (
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn sm primary" disabled={busy}
                onClick={() => act(() => api.approveProposal(draft.id), 'Study plan adopted. Progress is tracked from today’s numbers.')}>
                Adopt this plan
              </button>
              <button className="btn sm ghost" disabled={busy}
                onClick={() => act(() => api.rejectProposal(draft.id, 'Rejected in the student record'), 'Draft rejected. You can ask for another.')}>
                Reject
              </button>
            </div>
          ) : (
            <div className="sub">Waiting for the support office to adopt or reject it.</div>
          )}
        </div>
      ))}

      {!plan && drafts.length === 0 && (
        running ? (
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <Pill kind="accent">drafting…</Pill>
            <span className="sub">The agent is reading every assignment. This takes about a minute and updates by itself.</span>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {last && last.proposals === 0 && (
              <div className="sub">
                The last attempt ({day(last.started_at?.slice(0, 10) ?? null)}) produced no plan
                {last.error ? `: ${last.error}` : last.summary ? `. It said: “${last.summary.slice(0, 200)}”` : '.'}
                {' '}<a href="#/agents">Read the transcript</a>.
              </div>
            )}
            <input className="inp" value={note} aria-label={`Anything the agent should know about ${row.code}`}
              placeholder="Anything the agent should know (optional), e.g. has a tutor on Tuesdays"
              onChange={(e) => setNote(e.target.value)} />
            <div>
              <button className="btn sm primary" disabled={busy || !canDraft || !can('drafts.request')}
                onClick={() => act(() => api.draftStudyPlan(sid, row.code, note), 'Drafting started.')}>
                Draft a study plan with the AI agent
              </button>
            </div>
          </div>
        )
      )}
    </div>
  )
}

function Assignments({ sid, code }: { sid: string; code: string }) {
  const { data, error, loading, reload } = useApi(() => api.classWork(sid, code), [sid, code])
  if (loading) return <Loading what="assignments" />
  if (error) return <ErrorNote error={error} onRetry={reload} />
  if (!data) return null
  return (
    <>
      <table className="tbl" style={{ minWidth: 0 }}>
        <caption className="visually-hidden">Strands in {code}: this student against the class</caption>
        <thead>
          <tr>
            <th scope="col">Strand</th>
            <th scope="col" className="num">Gradebook</th>
            <th scope="col" className="num">Handed in</th>
            <th scope="col" className="num">Class</th>
            <th scope="col" className="num">Missing</th>
          </tr>
        </thead>
        <tbody>
          {data.strands.map((s) => (
            <tr key={s.strand}>
              <td>{s.strand}</td>
              <td className="num"><b>{pctText(s.pct)}</b></td>
              <td className="num">{s.handed_in_pct !== null ? pctText(s.handed_in_pct) : '—'}</td>
              <td className="num">{s.class_pct !== null ? pctText(s.class_pct) : '—'}</td>
              <td className="num">{s.missing || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="tbl" style={{ minWidth: 0 }}>
        <caption className="visually-hidden">Every past-due assignment in {code}</caption>
        <thead>
          <tr>
            <th scope="col">Assignment</th>
            <th scope="col" className="num">Score</th>
            <th scope="col" className="num">Class</th>
          </tr>
        </thead>
        <tbody>
          {[...data.assignments].reverse().map((a) => (
            <tr key={a.id}>
              <td>
                {a.title}
                <div className="sub">{a.kind} · {a.strand} · due {day(a.due_on)}{a.late ? ' · late' : ''}</div>
              </td>
              <td className="num">
                {a.pct === null ? <Pill kind="critical">missing</Pill> : <b>{pctText(a.pct)}</b>}
              </td>
              <td className="num">{a.class_pct !== null ? pctText(a.class_pct) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function PlanBody({ diagnosis, strands, sessions, goal, catchUp }: {
  diagnosis: string; strands: string[]; sessions: string[]; goal: string; catchUp: number
}) {
  return (
    <>
      <p style={{ margin: 0, fontSize: 12.5 }}>{diagnosis}</p>
      {strands.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="sub">Focus:</span>
          {strands.map((s) => <Pill key={s} kind="accent">{s}</Pill>)}
        </div>
      )}
      <ol style={{ margin: 0, paddingLeft: 20, fontSize: 12.5, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {sessions.map((s) => <li key={s}>{s}</li>)}
      </ol>
      {catchUp > 0 && <div className="sub">{catchUp} missing assignment{catchUp === 1 ? '' : 's'} to hand in.</div>}
      <div style={{ fontSize: 12.5 }}><b>Goal:</b> {goal}</div>
    </>
  )
}

function ActivePlan({ plan, busy, onClose }: {
  plan: StudyPlan; busy: boolean; onClose: (status: 'completed' | 'retired', outcome: string) => void
}) {
  const canClose = useAuth().can('plans.write')
  const [outcome, setOutcome] = useState('')
  const [closing, setClosing] = useState(false)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, borderTop: '1px solid var(--rule)', paddingTop: 9 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <Pill kind="good">Active</Pill>
        <b style={{ fontSize: 13.5 }}>{plan.title}</b>
      </div>
      <div className="sub">Owned by {plan.owner} · adopted {day(plan.opened_on)} · review {day(plan.review_on)}</div>
      <PlanBody diagnosis={plan.diagnosis} strands={plan.focus_strands} sessions={plan.sessions}
        goal={plan.goal} catchUp={0} />
      {plan.catch_up.length > 0 && (
        <div style={{ fontSize: 12.5 }}>
          <b>Hand in:</b> {plan.catch_up.map((a) => `${a.title} (due ${day(a.due_on)})`).join('; ')}
        </div>
      )}
      <table className="tbl" style={{ minWidth: 0 }}>
        <caption className="visually-hidden">Progress since the study plan was adopted</caption>
        <thead>
          <tr>
            <th scope="col">Measure</th>
            <th scope="col" className="num">At adoption</th>
            <th scope="col" className="num">Now</th>
            <th scope="col" className="num">Change</th>
          </tr>
        </thead>
        <tbody>
          {plan.progress.map((r) => (
            <tr key={r.measure}>
              <td>{r.measure}</td>
              <td className="num">{r.baseline !== null ? `${Math.round(r.baseline)}${r.unit}` : '—'}</td>
              <td className="num">{r.now !== null ? `${Math.round(r.now)}${r.unit}` : '—'}</td>
              <td className="num">
                {r.change === null ? '—' : r.unit ? <Delta value={r.change} /> : r.change > 0 ? `+${r.change}` : r.change}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {closing ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <input className="inp" value={outcome} aria-label="What happened"
            placeholder="What happened, e.g. handed in both unit tests, word problems up to 70%"
            onChange={(e) => setOutcome(e.target.value)} />
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn sm primary" disabled={busy} onClick={() => onClose('completed', outcome)}>Mark complete</button>
            <button className="btn sm" disabled={busy} onClick={() => onClose('retired', outcome)}>Retire without finishing</button>
            <button className="btn sm ghost" onClick={() => setClosing(false)}>Cancel</button>
          </div>
        </div>
      ) : canClose && (
        <div><button className="btn sm" onClick={() => setClosing(true)}>Close this plan…</button></div>
      )}
    </div>
  )
}
