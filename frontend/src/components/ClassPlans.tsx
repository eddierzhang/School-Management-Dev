import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { useCan } from '../auth'
import { useApi } from '../useApi'
import type { ClassImprovement, ClassPlan, ClassStatus, PlanDraft, StatusKind } from '../types'
import { Delta, ErrorNote, Icon, Loading, Pill, RejectButton } from './ui'

const STATUS: Record<ClassStatus, { kind: StatusKind; label: string }> = {
  'needs-plan': { kind: 'critical', label: 'Needs a plan' },
  watch: { kind: 'warning', label: 'Worth watching' },
  strong: { kind: 'good', label: 'Doing well' },
  'no-data': { kind: 'neutral', label: 'Nothing graded yet' },
}

const day = (iso: string | null) =>
  iso ? new Date(iso + (iso.length === 10 ? 'T00:00:00' : '')).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—'

/** A class's improvement plan: what the numbers say, the agent's draft, the adopted plan and its progress. */
export function ClassPlans({ code }: { code: string }) {
  const [tick, setTick] = useState(0)
  const data = useApi(() => api.improvement(code), [code, tick])
  const fleet = useApi(() => api.runtime(), [])
  const canRequest = useCan('drafts.request')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const reload = () => setTick((n) => n + 1)

  const running = data.data?.latest_run?.status === 'running'
  // Drafting takes a minute or more on a local model; poll only while it runs.
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
      reload()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That did not go through.')
      reload()
    } finally { setBusy(false) }
  }

  if (data.loading && !data.data) return <section className="sec"><Loading what="the improvement plan" /></section>
  if (data.error) return <section className="sec"><ErrorNote error={data.error} onRetry={reload} /></section>
  if (!data.data) return null
  const d: ClassImprovement = data.data
  const perf = d.performance
  const active = d.plans.find((p) => p.status === 'active')
  const past = d.plans.filter((p) => p.status !== 'active')
  const status = STATUS[perf.status]
  const rt = fleet.data?.runtime
  const canDraft = !!rt?.can_run_agents
  const last = d.latest_run

  return (
    <section className="sec">
      <div className="sec-head">
        <h2>Improvement plan</h2>
        <Pill kind={status.kind}>{status.label}</Pill>
      </div>
      <p className="sec-note">
        A plan for the class, not one student: what to teach differently, who does it, and a number
        to reach in four weeks. The class improvement agent drafts it from the figures below. Every
        percentage it cites must match them, and nothing takes effect until you adopt it.
      </p>

      {error && <ErrorNote error={error} />}
      {message && (
        <div className="banner" style={{ background: 'var(--accent-wash)', border: '1px solid var(--accent)' }}>
          <Icon name="good" /><span style={{ flex: 1 }}>{message}</span>
        </div>
      )}

      <div className="split">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
          {active && <ActivePlan plan={active} busy={busy}
            onClose={(s, outcome) => act(() => api.closeClassPlan(active.id, s, outcome),
              s === 'completed' ? 'Plan marked complete.' : 'Plan retired.')} />}

          {!active && d.drafts.map((draft) => (
            <Draft key={draft.id} draft={draft} busy={busy}
              onAdopt={() => act(() => api.approveProposal(draft.id), 'Plan adopted. Progress is tracked from today’s numbers.')}
              onReject={(note) => act(() => api.rejectProposal(draft.id, note),
                'Draft rejected. You can ask for another.')} />
          ))}

          {!active && d.drafts.length === 0 && (
            <div className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {running ? (
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <Pill kind="accent">drafting…</Pill>
                  <span className="sub">
                    The agent is reading {perf.code}. This takes about a minute on the local model and
                    updates by itself.
                  </span>
                </div>
              ) : (
                <>
                  <b style={{ fontSize: 13.5 }}>
                    {perf.status === 'strong' ? 'No plan needed, but you can ask for one.' : 'No plan yet.'}
                  </b>
                  {last && last.status !== 'running' && last.proposals === 0 && (
                    <div className="sub">
                      The last attempt ({day(last.started_at?.slice(0, 10) ?? null)}) produced no plan
                      {last.error ? `: ${last.error}` : last.summary ? `. It said: “${last.summary.slice(0, 240)}”` : '.'}
                      {' '}<a href="#/agents">Read the transcript</a>.
                    </div>
                  )}
                  <div className="field">
                    <label htmlFor={`plan-note-${code}`}>Anything the agent should know (optional)</label>
                    <textarea id={`plan-note-${code}`} className="inp" rows={2} value={note}
                      placeholder="e.g. the teacher is out the week of the 21st"
                      onChange={(e) => setNote(e.target.value)} />
                  </div>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                    <button className="btn primary" disabled={busy || !canDraft || !canRequest || perf.status === 'no-data'}
                      onClick={() => act(() => api.draftClassPlan(code, note), 'Drafting started.')}>
                      Draft a plan with the AI agent
                    </button>
                    {rt && !canDraft && (
                      <span className="sub">
                        {rt.reachable ? `${rt.model} cannot call tools, so it cannot draft.` : 'Ollama is not running, so nothing can be drafted.'}
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>
          )}

          {past.length > 0 && (
            <details>
              <summary className="sub" style={{ cursor: 'pointer' }}>Earlier plans ({past.length})</summary>
              {past.map((p) => (
                <div key={p.id} style={{ marginTop: 8 }}>
                  <b style={{ fontSize: 13 }}>{p.title}</b>{' '}
                  <span className="sub">{p.status} {day(p.closed_on)} · opened {day(p.opened_on)}</span>
                  {p.outcome && <div className="sub">{p.outcome}</div>}
                </div>
              ))}
            </details>
          )}
        </div>

        <div className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <h3 style={{ margin: 0, fontSize: 12, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>
            What the numbers say
          </h3>
          {perf.issues.length ? perf.issues.map((i) => (
            <div key={i} className="reason"><Icon name="warning" /><span>{i}</span></div>
          )) : <span className="sub">Nothing stands out: average, strands, work handed in and trend are all healthy.</span>}
          <dl className="kv">
            <dt>Class average</dt><dd>{perf.mean !== null ? `${Math.round(perf.mean)}%` : '—'}</dd>
            <dt>Work handed in</dt><dd>{perf.completion !== null ? `${Math.round(perf.completion * 100)}%` : '—'}</dd>
            <dt>Recent trend</dt><dd>{perf.trend !== null ? <Delta value={perf.trend} /> : '—'}</dd>
            <dt>Weakest strand</dt>
            <dd>{perf.strands[0] ? `${perf.strands[0].strand} ${Math.round(perf.strands[0].mean)}%` : '—'}</dd>
          </dl>
        </div>
      </div>
    </section>
  )
}

function PlanBody({ diagnosis, strands, actions, goal }: {
  diagnosis: string; strands: string[]; actions: string[]; goal: string
}) {
  return (
    <>
      <p style={{ margin: 0, fontSize: 13 }}>{diagnosis}</p>
      {strands.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="sub">Focus:</span>
          {strands.map((s) => <Pill key={s} kind="accent">{s}</Pill>)}
        </div>
      )}
      <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {actions.map((a) => <li key={a}>{a}</li>)}
      </ol>
      <div style={{ fontSize: 13 }}><b>Goal:</b> {goal}</div>
    </>
  )
}

function Draft({ draft, busy, onAdopt, onReject }: {
  draft: PlanDraft; busy: boolean; onAdopt: () => void; onReject: (note: string) => void
}) {
  const canDecide = useCan('plans.write')
  const p = draft.payload
  return (
    <div className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 10, borderColor: 'var(--accent)' }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <Pill kind="accent">Draft</Pill>
        <b style={{ fontSize: 14.5 }}>{p.title}</b>
      </div>
      <PlanBody diagnosis={p.diagnosis} strands={p.focus_strands} actions={p.actions} goal={p.goal} />
      <div className="sub">
        Drafted by the class improvement agent{draft.run_id !== null && <> · run #{draft.run_id}, <a href="#/agents">transcript</a></>}.
        Every figure it cites was checked against the class data.
      </div>
      {canDecide ? (
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn primary" disabled={busy} onClick={onAdopt}>Adopt this plan</button>
          <RejectButton busy={busy} small={false} onReject={onReject} />
        </div>
      ) : (
        <div className="sub">Waiting for the support office to adopt or reject it.</div>
      )}
    </div>
  )
}

function ActivePlan({ plan, busy, onClose }: {
  plan: ClassPlan; busy: boolean; onClose: (status: 'completed' | 'retired', outcome: string) => void
}) {
  const canClose = useCan('plans.write')
  const [outcome, setOutcome] = useState('')
  const [closing, setClosing] = useState(false)
  return (
    <div className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <Pill kind="good">Active</Pill>
        <b style={{ fontSize: 14.5 }}>{plan.title}</b>
      </div>
      <div className="sub">
        Owned by {plan.owner} · adopted {day(plan.opened_on)} · review {day(plan.review_on)}
      </div>
      <PlanBody diagnosis={plan.diagnosis} strands={plan.focus_strands} actions={plan.actions} goal={plan.goal} />

      <table className="tbl" style={{ minWidth: 0 }}>
        <caption className="visually-hidden">Progress since the plan was adopted</caption>
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
              <td className="num">{r.baseline !== null ? `${Math.round(r.baseline)}%` : '—'}</td>
              <td className="num">{r.now !== null ? `${Math.round(r.now)}%` : '—'}</td>
              <td className="num">{r.change !== null ? <Delta value={r.change} /> : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {closing ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="field">
            <label htmlFor={`outcome-${plan.id}`}>What happened</label>
            <textarea id={`outcome-${plan.id}`} className="inp" rows={2} value={outcome}
              placeholder="e.g. word problems up to 74% on the unit test"
              onChange={(e) => setOutcome(e.target.value)} />
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn primary" disabled={busy} onClick={() => onClose('completed', outcome)}>Mark complete</button>
            <button className="btn" disabled={busy} onClick={() => onClose('retired', outcome)}>Retire without finishing</button>
            <button className="btn ghost" onClick={() => setClosing(false)}>Cancel</button>
          </div>
        </div>
      ) : canClose && (
        <div><button className="btn sm" onClick={() => setClosing(true)}>Close this plan…</button></div>
      )}
    </div>
  )
}
