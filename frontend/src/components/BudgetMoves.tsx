import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { useApi } from '../useApi'
import type { AgentRun, BudgetLine, BudgetMove, ProposalRow } from '../types'
import { ErrorNote, Icon, Pill, RejectButton } from './ui'

const money = (n: number) => (n < 0 ? '-$' : '$') + Math.abs(Math.round(n)).toLocaleString('en-US')

const FINANCE_KINDS: Record<string, string> = {
  budget_revision: 'Budget revision',
  budget_line: 'Open a line',
  budget_transfer: 'Transfer',
  transaction_review: 'Hold a charge',
}

/** Where money is needed, the finance agent's proposals to move it, and opening a new line. */
export function BudgetMoves({ lines, onChanged }: { lines: BudgetLine[]; onChanged: () => void }) {
  const [tick, setTick] = useState(0)
  const needs = useApi(() => api.financeNeeds(), [tick])
  const proposals = useApi(() => api.proposals('pending'), [tick])
  const runs = useApi(() => api.runs('finance'), [tick])
  const fleet = useApi(() => api.runtime(), [])
  const [task, setTask] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [opening, setOpening] = useState(false)

  const refresh = useCallback(() => { setTick((n) => n + 1); onChanged() }, [onChanged])
  const mine = (proposals.data ?? []).filter((p) => p.agent === 'finance' && p.kind in FINANCE_KINDS)
  const active = (runs.data ?? []).find((r: AgentRun) => r.status === 'running' || r.status === 'queued')
  const last = (runs.data ?? [])[0]

  // Agent runs take a minute or three on the local model; poll only while one is in flight.
  useEffect(() => {
    if (!active) return
    const t = window.setInterval(() => setTick((n) => n + 1), 3000)
    return () => window.clearInterval(t)
  }, [active])

  /** `fn` may return the message to show; otherwise `done` is shown. */
  async function act(fn: () => Promise<unknown>, done: string) {
    setBusy(true); setError(null); setNotice(null)
    try {
      const said = await fn()
      setNotice(typeof said === 'string' ? said : done)
      refresh()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That did not go through.')
      refresh()
    } finally { setBusy(false) }
  }

  const rt = fleet.data?.runtime
  const n = needs.data
  const totalNeed = (n?.needs ?? []).reduce((a, x) => a + x.need, 0)
  const totalRoom = (n?.room ?? []).reduce((a, x) => a + x.can_give, 0)

  return (
    <section className="sec">
      <div className="sec-head">
        <h2>Moving money to where it is needed</h2>
        <span className="spacer" />
        <button className="btn" onClick={() => setOpening(true)}>Open a new line</button>
      </div>
      <p className="sec-note">
        No approved allocation is ever edited. A revision is a set of transfers approved together, and a
        new line opens at zero and is funded by a transfer, so the original budget stays readable beside
        every change. The finance agent proposes; nothing moves until you approve.
      </p>
      {error && <ErrorNote error={error} />}
      {notice && (
        <div className="banner" style={{ background: 'var(--accent-wash)', border: '1px solid var(--accent)' }}>
          <Icon name="good" /><span style={{ flex: 1 }}>{notice}</span>
        </div>
      )}

      <div className="split">
        <div className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
          <div className="eyebrow">Needs money · {money(totalNeed)}</div>
          {n && n.needs.length === 0 && <span className="sub">No line is short.</span>}
          {n?.needs.map((x) => (
            <div key={x.code} style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
              <b style={{ minWidth: 70, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{money(x.need)}</b>
              <div style={{ minWidth: 0 }}>
                <span className="code">{x.code}</span> {x.name}
                <div className="sub">{x.reasons.join('; ')}</div>
              </div>
            </div>
          ))}
          <div className="eyebrow" style={{ marginTop: 6 }}>Can give · {money(totalRoom)}</div>
          <div className="sub">
            {(n?.room ?? []).map((r) => `${r.code} up to ${money(r.can_give)}`).join(' · ') || 'No line has room to give.'}
          </div>
          <div className="sub">
            "Can give" is the most a line can lose and still be on track for the year.
          </div>
        </div>

        <div className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
          <div className="eyebrow">Finance agent</div>
          {active ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Pill kind="accent">{active.status === 'running' ? 'working…' : 'queued'}</Pill>
              <span className="sub">Reading the budget. This takes a minute or three and updates by itself.</span>
            </div>
          ) : (
            <>
              <div className="field">
                <label htmlFor="fin-task">Tell it what to do (optional)</label>
                <textarea id="fin-task" className="inp" rows={2} value={task}
                  placeholder="Blank: find where money is needed, propose a revision, and flag suspicious charges"
                  onChange={(e) => setTask(e.target.value)} />
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <button className="btn primary" disabled={busy || !rt?.can_run_agents}
                  onClick={() => act(() => api.runAgent('finance', task.trim() || undefined),
                    'The finance agent is working. Its proposals will appear below.')}>
                  Run the finance agent
                </button>
                {rt && !rt.can_run_agents && <span className="sub">The local model is not available.</span>}
              </div>
              {last && last.status !== 'running' && last.proposals === 0 && (
                <div className="sub">
                  The last run proposed nothing{last.error ? `: ${last.error}` : last.summary ? `: “${last.summary.slice(0, 200)}”` : '.'}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {mine.length > 0 && (
        <div className="panelbox queue" style={{ marginTop: 16 }}>
          {mine.map((p) => (
            <div className="qrow" key={p.id} style={{ ['--sev' as string]: 'var(--signal)' }}>
              <div className="qbody">
                <div className="qtitle">{p.summary}</div>
                <div className="qmeta">{p.reason}</div>
                <ProposalDetail p={p} />
                <div className="sub" style={{ marginTop: 3 }}>
                  {FINANCE_KINDS[p.kind]} · proposed by the finance agent{p.run_id !== null && <> · run #{p.run_id}</>}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end', maxWidth: 440 }}>
                <button className="btn sm primary" disabled={busy}
                  onClick={() => act(async () => (await api.approveProposal(p.id)).result, 'Approved.')}>Approve</button>
                <RejectButton busy={busy}
                  onReject={(note) => act(() => api.rejectProposal(p.id, note), 'Rejected. Nothing moved.')} />
              </div>
            </div>
          ))}
        </div>
      )}

      {opening && (
        <OpenLineDialog lines={lines} room={n?.room ?? []} onClose={() => setOpening(false)}
          onOpened={(msg) => { setOpening(false); setNotice(msg); refresh() }} />
      )}
    </section>
  )
}

function ProposalDetail({ p }: { p: ProposalRow }) {
  if (p.kind === 'budget_revision') {
    const moves = (p.payload.moves ?? []) as BudgetMove[]
    return (
      <table className="tbl" style={{ minWidth: 0, marginTop: 6, maxWidth: 460 }}>
        <thead><tr><th scope="col">From</th><th scope="col">To</th><th scope="col" className="num">Amount</th></tr></thead>
        <tbody>
          {moves.map((m, i) => (
            <tr key={i}>
              <td className="code">{m.from_line}</td>
              <td className="code">{m.to_line}</td>
              <td className="num">{money(m.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }
  if (p.kind === 'budget_line') {
    const d = p.payload as Record<string, string | number>
    return (
      <div className="sub" style={{ marginTop: 4 }}>
        New line <span className="code">{d.code}</span> · {d.department} · {d.category} · funded with{' '}
        {money(Number(d.amount))} from <span className="code">{d.from_line}</span>
      </div>
    )
  }
  return null
}

function OpenLineDialog({ lines, room, onClose, onOpened }: {
  lines: BudgetLine[]
  room: { code: string; name: string; can_give: number }[]
  onClose: () => void
  onOpened: (message: string) => void
}) {
  const depts = [...new Set(lines.map((l) => l.department))].sort()
  const cats = [...new Set(lines.map((l) => l.category))].sort()
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [dept, setDept] = useState(depts[0] ?? '')
  const [cat, setCat] = useState(cats[0] ?? '')
  const [from, setFrom] = useState(room[0]?.code ?? '')
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const max = room.find((r) => r.code === from)?.can_give ?? 0
  const valid = /^[A-Za-z]{2,4}-[A-Za-z]{3}$/.test(code) && name.trim().length >= 4 && Number(amount) > 0
    && reason.trim().length >= 4 && from

  async function save() {
    setSaving(true); setError(null)
    try {
      const line = await api.openBudgetLine({
        code: code.toUpperCase(), name: name.trim(), department: dept, category: cat,
        from_line: from, amount: Number(amount), reason: reason.trim(),
      })
      onOpened(`Opened ${line.code} with ${money(line.budget)} from ${from}.`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The line could not be opened.')
    } finally { setSaving(false) }
  }

  return (
    <>
      <button className="scrim" style={{ zIndex: 60 }} onClick={onClose} aria-label="Cancel" />
      <aside className="drawer" style={{ zIndex: 70, width: 'min(460px, 100%)' }} role="dialog" aria-modal="true" aria-labelledby="open-line-title">
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id="open-line-title">Open a new budget line</h2>
            <div className="sub" style={{ marginTop: 3 }}>Starts at zero and is funded by a transfer from a line with room.</div>
          </div>
          <button className="btn sm ghost" onClick={onClose}>Close</button>
        </div>
        <div className="drawer-body">
          {error && <ErrorNote error={error} />}
          <div className="field">
            <label htmlFor="ol-code">Code</label>
            <input id="ol-code" className="inp" value={code} placeholder="MAT-WKS" onChange={(e) => setCode(e.target.value.toUpperCase())} />
          </div>
          <div className="field">
            <label htmlFor="ol-name">What the money is for</label>
            <input id="ol-name" className="inp" value={name} placeholder="Word-problems workshops" onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="ol-dept">Department</label>
            <select id="ol-dept" className="inp" value={dept} onChange={(e) => setDept(e.target.value)}>
              {depts.map((d) => <option key={d}>{d}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="ol-cat">Category</label>
            <select id="ol-cat" className="inp" value={cat} onChange={(e) => setCat(e.target.value)}>
              {cats.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="ol-from">Fund it from</label>
            <select id="ol-from" className="inp" value={from} onChange={(e) => setFrom(e.target.value)}>
              {room.map((r) => <option key={r.code} value={r.code}>{r.code} · {r.name} (up to {money(r.can_give)})</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="ol-amount">Amount</label>
            <input id="ol-amount" className="inp" type="number" min={1} value={amount} onChange={(e) => setAmount(e.target.value)} />
            {from && <span className="sub">{from} can give up to {money(max)} and stay on track.</span>}
          </div>
          <div className="field">
            <label htmlFor="ol-why">Why</label>
            <textarea id="ol-why" className="inp" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        </div>
        <div className="drawer-foot">
          <button className="btn primary" disabled={saving || !valid} onClick={save}>{saving ? 'Opening…' : 'Open the line'}</button>
          <button className="btn ghost" onClick={onClose}>Cancel</button>
        </div>
      </aside>
    </>
  )
}
