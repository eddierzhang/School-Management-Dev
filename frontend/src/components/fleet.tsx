import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { useApi } from '../useApi'
import type { AgentRun, Fleet, ProposalRow, TranscriptStep } from '../types'
import { ErrorNote, Icon, Loading, Pill } from './ui'

/* The fleet's state lives here so the home page and the Agents tab share one
   implementation and one poller, rather than two that can disagree. */

const KIND_LABEL: Record<string, string> = {
  requisition: 'Order stock',
  reorder_point: 'Change reorder point',
  new_section: 'Open a section',
  capacity_change: 'Change capacity',
  support_plan: 'Open a support plan',
  budget_transfer: 'Move budget',
  transaction_review: 'Hold a charge for review',
  class_plan: 'Adopt a class improvement plan',
}

/** Shown in the run hint; the shortcut itself accepts either modifier. */
const MODIFIER = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
  ? '\u2318' : 'Ctrl'

export const secs = (ms: number) => (ms >= 1000 ? `${Math.round(ms / 1000)}s` : `${ms}ms`)

export interface FleetState {
  fleet: Fleet | null
  fleetLoading: boolean
  fleetError: string | null
  reloadFleet: () => void
  runs: AgentRun[]
  proposals: ProposalRow[]
  tasks: Record<string, string>
  setTasks: (fn: (t: Record<string, string>) => Record<string, string>) => void
  busy: string | null
  error: string | null
  notice: string | null
  openRun: AgentRun | null
  setOpenRun: (r: AgentRun | null) => void
  start: (name: string) => Promise<void>
  decide: (p: ProposalRow, approve: boolean) => Promise<void>
  refresh: () => Promise<void>
}

/**
 * @param onApplied called after a proposal is applied or rejected, so counts
 * elsewhere in the app (open support plans, low stock) refetch rather than
 * sitting stale until the next navigation.
 */
export function useFleet(onApplied?: () => void): FleetState {
  const fleet = useApi(() => api.fleet(), [])
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [proposals, setProposals] = useState<ProposalRow[]>([])
  const [openRun, setOpenRun] = useState<AgentRun | null>(null)
  const [tasks, setTasks] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [r, p] = await Promise.all([api.runs(), api.proposals('pending')])
      setRuns(r)
      setProposals(p)
      setOpenRun((cur) => (cur ? r.find((x) => x.id === cur.id) ?? cur : cur))
    } catch { /* transient; the next poll retries */ }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  // Runs take minutes locally, so poll only while something is in flight.
  useEffect(() => {
    if (!runs.some((r) => r.status === 'running')) {
      if (timer.current) { window.clearInterval(timer.current); timer.current = null }
      return
    }
    timer.current = window.setInterval(() => { void refresh() }, 3000)
    return () => { if (timer.current) window.clearInterval(timer.current) }
  }, [runs, refresh])

  const start = useCallback(async (name: string) => {
    setBusy(name); setError(null); setNotice(null)
    try {
      await api.runAgent(name, tasks[name]?.trim() || undefined)
      setNotice(`${name} started. Local inference takes a few minutes — this updates itself.`)
      await refresh()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not start that agent.')
    } finally { setBusy(null) }
  }, [tasks, refresh])

  const decide = useCallback(async (p: ProposalRow, approve: boolean) => {
    setError(null); setNotice(null)
    try {
      if (approve) {
        const res = await api.approveProposal(p.id)
        setNotice(res.result)
      } else {
        await api.rejectProposal(p.id)
        setNotice('Proposal rejected. Nothing was changed.')
      }
      await refresh()
      onApplied?.()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That could not be applied.')
      await refresh()
    }
  }, [refresh, onApplied])

  return {
    fleet: fleet.data, fleetLoading: fleet.loading, fleetError: fleet.error,
    reloadFleet: fleet.reload,
    runs, proposals, tasks, setTasks, busy, error, notice, openRun, setOpenRun,
    start, decide, refresh,
  }
}

export function RuntimeNotice({ f }: { f: FleetState }) {
  const rt = f.fleet?.runtime
  if (!rt) return null
  if (!rt.reachable) {
    return (
      <div className="banner critical">
        <Icon name="critical" />
        <span style={{ flex: 1, minWidth: 240 }}>
          <b>Ollama is not reachable.</b> {rt.error} Start it with <span className="code">ollama serve</span>.
        </span>
      </div>
    )
  }
  if (!rt.can_run_agents) {
    return (
      <div className="banner critical">
        <Icon name="critical" />
        <span style={{ flex: 1, minWidth: 240 }}>
          <b>{rt.model} cannot call tools</b>, so it cannot drive an agent
          {rt.capabilities?.length ? <> (it reports: {rt.capabilities.join(', ')})</> : null}. Install a
          tool-capable model — <span className="code">ollama pull qwen3:4b</span> — and set{' '}
          <span className="code">HR_OLLAMA_MODEL</span>.
        </span>
      </div>
    )
  }
  return null
}

export function FleetMessages({ f }: { f: FleetState }) {
  return (
    <>
      {f.error && <ErrorNote error={f.error} />}
      {f.notice && (
        <div className="banner" style={{ background: 'var(--accent-wash)', border: '1px solid var(--accent)' }}>
          <span style={{ flex: 1 }}>{f.notice}</span>
        </div>
      )}
    </>
  )
}

export function FleetCards({ f }: { f: FleetState }) {
  if (f.fleetLoading) return <Loading what="the fleet" />
  if (f.fleetError) return <ErrorNote error={f.fleetError} onRetry={f.reloadFleet} />
  if (!f.fleet) return null
  const rt = f.fleet.runtime

  return (
    <div className="cards">
      {f.fleet.agents.map((a) => {
        const running = f.runs.find((r) => r.agent === a.name && r.status === 'running')
        return (
          <article className="icard" key={a.name}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h3>{a.title}</h3>
                <div className="sub">{a.domain}</div>
              </div>
              {running && <Pill kind="accent">working…</Pill>}
            </div>
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
              {a.tools.map((t) => (
                <span key={t.name} className="code"
                  style={{
                    fontSize: 10.5, padding: '1px 6px', borderRadius: 4,
                    border: '1px solid var(--rule-strong)',
                    background: t.proposes ? 'var(--signal-wash)' : 'var(--card-2)',
                    color: t.proposes ? 'var(--signal-ink)' : 'var(--ink-2)',
                  }}
                  title={t.proposes ? `Proposes: ${t.proposes}` : t.description}>
                  {t.name}
                </span>
              ))}
            </div>
            <div className="field">
              <label htmlFor={`task-${a.name}`}>Tell it what to do</label>
              <textarea
                id={`task-${a.name}`} className="inp" rows={3}
                placeholder={a.default_task}
                value={f.tasks[a.name] ?? ''}
                disabled={!rt.can_run_agents}
                onChange={(e) => f.setTasks((t) => ({ ...t, [a.name]: e.target.value }))}
                onKeyDown={(e) => {
                  const ready = rt.can_run_agents && f.busy !== a.name && !running
                  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && ready) {
                    e.preventDefault()
                    void f.start(a.name)
                  }
                }}
              />
            </div>
            <div style={{ marginTop: 'auto', paddingTop: 4, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <button className="btn primary"
                disabled={!rt.can_run_agents || f.busy === a.name || !!running}
                onClick={() => void f.start(a.name)}>
                {running ? 'Running…' : f.busy === a.name ? 'Starting…' : 'Run agent'}
              </button>
              <span className="sub">
                {f.tasks[a.name]?.trim() ? `${MODIFIER}+Enter to run` : 'Blank runs the sweep above'}
              </span>
            </div>
          </article>
        )
      })}
    </div>
  )
}

export function ProposalInbox({ f, emptyNote = true }: { f: FleetState; emptyNote?: boolean }) {
  if (f.proposals.length === 0) {
    return emptyNote
      ? <div className="panelbox"><div className="qempty">No proposals are waiting. Run an agent above.</div></div>
      : null
  }
  return (
    <div className="panelbox queue">
      {f.proposals.map((p) => (
        <div className="qrow" key={p.id} style={{ ['--sev' as string]: 'var(--signal)' }}>
          <div className="qbody">
            <div className="qtitle">{p.summary}</div>
            <div className="qmeta">{p.reason}</div>
            <div className="sub" style={{ marginTop: 3 }}>
              {KIND_LABEL[p.kind] ?? p.kind} · proposed by the {p.agent} agent
              {p.run_id !== null && <> · run #{p.run_id}</>}
            </div>
            {p.evidence.length > 0 && (
              <details style={{ marginTop: 4 }}>
                <summary className="sub" style={{ cursor: 'pointer' }}>Evidence it used</summary>
                <pre style={{
                  fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--ink-2)',
                  background: 'var(--card-2)', padding: 9, borderRadius: 6,
                  overflowX: 'auto', marginTop: 5,
                }}>{JSON.stringify(p.evidence, null, 1)}</pre>
              </details>
            )}
          </div>
          <button className="btn sm primary" onClick={() => void f.decide(p, true)}>Approve</button>
          <button className="btn sm ghost" onClick={() => void f.decide(p, false)}>Reject</button>
        </div>
      ))}
    </div>
  )
}

function Transcript({ steps }: { steps: TranscriptStep[] }) {
  if (!steps.length) return <p className="sub" style={{ margin: 0 }}>No steps recorded.</p>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {steps.map((s) => (
        <div key={s.step} style={{ borderLeft: '2px solid var(--rule)', paddingLeft: 11 }}>
          <div className="sub" style={{ fontWeight: 600 }}>
            {s.step === 0 ? 'Opening read (automatic)' : s.step === 'harvest' ? 'Harvest (constrained JSON)' : `Step ${s.step}`}
            {s.ms > 0 && <> · {secs(s.ms)}</>}
            {s.recovered_from_text && <> · <span style={{ color: 'var(--serious)' }}>tool call recovered from prose</span></>}
            {s.nudged && <> · <span style={{ color: 'var(--serious)' }}>nudged to record it</span></>}
          </div>
          {s.calls.map((c, i) => (
            <div key={i} style={{ marginTop: 5, fontSize: 12 }}>
              <span className="code">{c.tool}</span>
              <span className="sub"> {JSON.stringify(c.arguments).slice(0, 90)}</span>
              {c.ok === false && (
                <div style={{ color: 'var(--critical)', marginTop: 2 }}>
                  {c.repeat ? 'repeated call — ' : 'rejected — '}{c.error}
                </div>
              )}
              {c.ok && c.result && (
                <div className="sub" style={{ marginTop: 2, fontFamily: 'var(--font-mono)', fontSize: 11, wordBreak: 'break-all' }}>
                  {c.result.slice(0, 200)}
                </div>
              )}
            </div>
          ))}
          {s.said && <div style={{ fontSize: 12.5, marginTop: 6 }}>{s.said.slice(0, 400)}</div>}
        </div>
      ))}
    </div>
  )
}

export function RunHistory({ f, limit }: { f: FleetState; limit?: number }) {
  const rows = limit ? f.runs.slice(0, limit) : f.runs
  if (rows.length === 0) {
    return <div className="panelbox"><div className="qempty">No agent has run yet.</div></div>
  }
  return (
    <div className="tblwrap">
      <table className="tbl" style={{ minWidth: 640 }}>
        <thead>
          <tr>
            <th scope="col">Run</th><th scope="col">Agent</th><th scope="col">Status</th>
            <th scope="col" className="num">Steps</th><th scope="col" className="num">Rejected calls</th>
            <th scope="col" className="num">Took</th><th scope="col" className="num">Proposals</th>
            <th scope="col" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td><span className="code">#{r.id}</span><div className="sub" style={{ maxWidth: 280 }}>{r.prompt.slice(0, 80)}</div></td>
              <td className="nowrap sub">{r.agent}</td>
              <td>
                {r.status === 'running' ? <Pill kind="accent">running</Pill>
                  : r.status === 'done' ? <Pill kind="good">done</Pill>
                  : <Pill kind="critical">failed</Pill>}
              </td>
              <td className="num">{r.steps_used}</td>
              <td className="num">{r.tool_errors || <span className="sub">—</span>}</td>
              <td className="num">{r.duration_ms ? secs(r.duration_ms) : '—'}</td>
              <td className="num">{r.proposals || <span className="sub">—</span>}</td>
              <td className="nowrap">
                <button className="btn sm" onClick={async () => f.setOpenRun(await api.run(r.id))}>
                  Transcript
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function RunDrawer({ f }: { f: FleetState }) {
  const run = f.openRun
  if (!run) return null
  return (
    <>
      <button className="scrim" onClick={() => f.setOpenRun(null)} aria-label="Close transcript" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="run-title">
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id="run-title">Run #{run.id} — {run.agent}</h2>
            <div className="sub" style={{ marginTop: 3 }}>
              {run.model} · {run.steps_used} steps · {secs(run.duration_ms)}
              {run.tool_errors > 0 && <> · {run.tool_errors} rejected call(s)</>}
            </div>
          </div>
          <button className="btn sm ghost" onClick={() => f.setOpenRun(null)}>Close</button>
        </div>
        <div className="drawer-body">
          <div className="block">
            <h3>Task</h3>
            <p style={{ margin: 0, fontSize: 12.5 }}>{run.prompt}</p>
          </div>
          {run.error && <ErrorNote error={run.error} />}
          {run.summary && (
            <div className="block">
              <h3>What it concluded</h3>
              <p style={{ margin: 0, fontSize: 12.5, whiteSpace: 'pre-wrap' }}>{run.summary.slice(0, 1500)}</p>
            </div>
          )}
          <div className="block">
            <h3>Every step it took</h3>
            <Transcript steps={run.transcript ?? []} />
          </div>
        </div>
      </aside>
    </>
  )
}
