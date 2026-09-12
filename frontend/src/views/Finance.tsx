import { useCallback, useState } from 'react'
import { api, ApiError } from '../api'
import { useApi } from '../useApi'
import type { Anomaly, BudgetLine, Txn } from '../types'
import { ErrorNote, Icon, Loading, Meter, Pill, Stat } from '../components/ui'

const money = (n: number, cents = false) => {
  const s = Math.abs(n).toLocaleString('en-US', {
    minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0,
  })
  return (n < 0 ? '-$' : '$') + s
}

function LineDrawer({ code, lines, onClose, onChanged }: {
  code: string; lines: BudgetLine[]; onClose: () => void; onChanged: () => void
}) {
  const { data, error, loading, reload } = useApi(() => api.budgetLine(code), [code])
  const [vendor, setVendor] = useState('')
  const [desc, setDesc] = useState('')
  const [amount, setAmount] = useState('')
  const [oneTime, setOneTime] = useState(false)
  const [from, setFrom] = useState('')
  const [moveAmount, setMoveAmount] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)

  async function run(fn: () => Promise<unknown>, done: string) {
    setBusy(true); setProblem(null); setNote(null)
    try { await fn(); setNote(done); reload(); onChanged() }
    catch (e) { setProblem(e instanceof ApiError ? e.message : 'That did not save.') }
    finally { setBusy(false) }
  }

  const donors = lines.filter((l) => l.code !== code && l.available > 0)

  return (
    <>
      <button className="scrim" onClick={onClose} aria-label="Close budget line" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="line-title">
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id="line-title">{data?.name ?? code}</h2>
            <div className="sub" style={{ marginTop: 3 }}>
              <span className="code">{code}</span>{data && <> · {data.department} · {data.owner}</>}
            </div>
          </div>
          <button className="btn sm ghost" onClick={onClose}>Close</button>
        </div>
        <div className="drawer-body">
          {loading && <Loading what="the budget line" />}
          {error && <ErrorNote error={error} onRetry={reload} />}
          {problem && <ErrorNote error={problem} />}
          {note && (
            <div className="banner" style={{ background: 'var(--accent-wash)', border: '1px solid var(--accent)', marginBottom: 0 }}>
              <span>{note}</span>
            </div>
          )}
          {data && (
            <>
              <div className="block">
                <Pill kind={data.status}>{data.status_label}</Pill>
                {data.note && <p className="sub" style={{ margin: 0 }}>{data.note}</p>}
                <dl className="kv">
                  <dt>Allocated</dt><dd>{money(data.allocated)}</dd>
                  {(data.transfers_in > 0 || data.transfers_out > 0) && (
                    <><dt>Transfers</dt><dd>+{money(data.transfers_in)} in · −{money(data.transfers_out)} out</dd></>
                  )}
                  <dt>Budget</dt><dd>{money(data.budget)}</dd>
                  <dt>Spent</dt><dd>{money(data.spent, true)}{data.one_time > 0 && <span className="sub"> · {money(data.one_time)} one-time</span>}</dd>
                  <dt>Committed</dt><dd>{money(data.committed, true)}</dd>
                  <dt>Available</dt><dd>{money(data.available, true)}</dd>
                  <dt>Projected by June</dt><dd>{money(data.projected)}</dd>
                </dl>
              </div>

              {data.commitments.length > 0 && (
                <div className="block">
                  <h3>Committed, not yet spent</h3>
                  <div className="people">
                    {data.commitments.map((c) => (
                      <div className="person" key={c.sku}>
                        <span className="pn">{c.name}<div className="sub"><span className="code">{c.sku}</span> · {c.source}</div></span>
                        <span className="nowrap">{money(c.amount, true)}</span>
                      </div>
                    ))}
                  </div>
                  <p className="sub" style={{ margin: 0 }}>From the stockroom's open requisition, costed to par.</p>
                </div>
              )}

              <div className="block">
                <h3>Transactions</h3>
                {data.transactions.length === 0 && <p className="sub" style={{ margin: 0 }}>Nothing posted yet.</p>}
                <div className="people">
                  {data.transactions.map((t) => (
                    <div className="person" key={t.id}>
                      <span className="pn">
                        {t.vendor}
                        <div className="sub">
                          #{t.id} · {t.posted_on} · {t.description}{t.reference && <> · <span className="code">{t.reference}</span></>}
                          {t.one_time && <> · one-time</>}
                        </div>
                        {t.review_note && <div className="sub">{t.review_note}</div>}
                      </span>
                      {t.review_status === 'flagged' && <Pill kind="serious">held</Pill>}
                      <span className="nowrap">{money(t.amount, true)}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="block">
                <h3>Record a charge</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 }}>
                  <div className="field"><label htmlFor="tx-vendor">Vendor</label>
                    <input id="tx-vendor" className="inp" value={vendor} onChange={(e) => setVendor(e.target.value)} /></div>
                  <div className="field"><label htmlFor="tx-amount">Amount ($)</label>
                    <input id="tx-amount" className="inp" type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} /></div>
                </div>
                <div className="field"><label htmlFor="tx-desc">What it was for</label>
                  <input id="tx-desc" className="inp" value={desc} onChange={(e) => setDesc(e.target.value)} /></div>
                <label className="toggle" htmlFor="tx-once">
                  <input id="tx-once" type="checkbox" checked={oneTime} onChange={(e) => setOneTime(e.target.checked)} />
                  One-time purchase (not part of the monthly pace)
                </label>
                <div>
                  <button className="btn primary" disabled={busy || !vendor || !desc || !amount}
                    onClick={() => void run(async () => {
                      await api.recordTransaction({ line_code: code, vendor, description: desc, amount: Number(amount), one_time: oneTime })
                      setVendor(''); setDesc(''); setAmount(''); setOneTime(false)
                    }, 'Charge recorded.')}>
                    Record charge
                  </button>
                </div>
              </div>

              <div className="block">
                <h3>Move money into this line</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 }}>
                  <div className="field"><label htmlFor="tr-from">From</label>
                    <select id="tr-from" className="inp" value={from} onChange={(e) => setFrom(e.target.value)}>
                      <option value="">Choose a line</option>
                      {donors.map((l) => <option key={l.code} value={l.code}>{l.code} — {money(l.available)} available</option>)}
                    </select></div>
                  <div className="field"><label htmlFor="tr-amount">Amount ($)</label>
                    <input id="tr-amount" className="inp" type="number" step="1" value={moveAmount} onChange={(e) => setMoveAmount(e.target.value)} /></div>
                </div>
                <div className="field"><label htmlFor="tr-reason">Reason</label>
                  <input id="tr-reason" className="inp" value={reason} onChange={(e) => setReason(e.target.value)} /></div>
                <div>
                  <button className="btn" disabled={busy || !from || !moveAmount || reason.length < 4}
                    onClick={() => void run(async () => {
                      await api.transfer({ from_line: from, to_line: code, amount: Number(moveAmount), reason })
                      setFrom(''); setMoveAmount(''); setReason('')
                    }, 'Transfer recorded.')}>
                    Move money
                  </button>
                </div>
                <p className="sub" style={{ margin: 0 }}>
                  The source line must have the money available and stay on track afterwards. The original
                  allocation is kept; transfers are recorded beside it.
                </p>
                {data.transfers.length > 0 && (
                  <div className="people">
                    {data.transfers.map((t) => (
                      <div className="person" key={t.id}>
                        <span className="pn">{t.from_line} → {t.to_line}<div className="sub">{t.reason} · {t.approved_by}</div></span>
                        <span className="nowrap">{money(t.amount, true)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </aside>
    </>
  )
}

export function Finance({ onChanged }: { onChanged?: () => void }) {
  const [nonce, setNonce] = useState(0)
  const [open, setOpen] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const bump = useCallback(() => { setNonce((n) => n + 1); onChanged?.() }, [onChanged])

  const summary = useApi(() => api.financeSummary(), [nonce])
  const lines = useApi(() => api.budgetLines(), [nonce])
  const found = useApi(() => api.anomalies(), [nonce])
  const held = useApi(() => api.flaggedTransactions(), [nonce])

  async function review(id: number, status: Txn['review_status'], note = '') {
    setProblem(null)
    try { await api.reviewTransaction(id, status, note); bump() }
    catch (e) { setProblem(e instanceof ApiError ? e.message : 'That did not save.') }
  }

  const s = summary.data
  const open_anomalies = (found.data ?? []).filter((a: Anomaly) => a.review_status === 'clear')
  const troubled = (lines.data ?? []).filter((l) => l.status === 'critical')

  return (
    <>
      <section className="sec">
        <div className="sec-head">
          <h2>Finance</h2>
          <span className="spacer" />
          {s && <span className="sub">{s.fiscal_year} · {s.elapsed_pct}% of the year gone</span>}
        </div>
        <p className="sec-note">
          Every line is judged against how much of the year has passed. Committed money — the
          stockroom's open requisition — counts before it is spent, so an approved order shows here
          the moment it is approved. One-time purchases are kept out of the monthly pace, or every
          front-loaded line would look like it will overspend.
        </p>
        {problem && <ErrorNote error={problem} />}

        {s && (
          <div className="strip" style={{ marginBottom: 16 }}>
            <Stat k="Budget" v={money(s.budget)} c={`${s.lines} lines`} />
            <Stat k="Spent" v={money(s.spent)} c={`${Math.round((s.spent / s.budget) * 100)}% of budget`} />
            <Stat k="Committed" v={money(s.committed)} c="on order, not yet paid" />
            <Stat k="Needs attention" v={s.over + s.at_risk}
              c={`${s.over} over · ${s.at_risk} at risk · ${s.anomalies} charge${s.anomalies === 1 ? '' : 's'} to check`} />
          </div>
        )}

        {troubled.length > 0 && (
          <div className="banner critical">
            <Icon name="critical" />
            <span style={{ flex: 1, minWidth: 200 }}>
              <b>{troubled.length === 1 ? `${troubled[0]?.name} is` : `${troubled.length} lines are`} over budget</b>
              {' '}counting open commitments. Open a line to move money into it.
            </span>
          </div>
        )}

        {lines.loading && <Loading what="the budget" />}
        {lines.error && <ErrorNote error={lines.error} onRetry={lines.reload} />}
        {lines.data && s && (
          <div className="tblwrap">
            <table className="tbl">
              <caption className="visually-hidden">Budget lines with spending against the year so far</caption>
              <thead>
                <tr>
                  <th scope="col">Line</th>
                  <th scope="col" className="num">Budget</th>
                  <th scope="col">Used vs year gone</th>
                  <th scope="col" className="num">Available</th>
                  <th scope="col" className="num">Projected by June</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {lines.data.map((l) => (
                  <tr key={l.code}>
                    <td>
                      <button className="rowbtn" onClick={() => setOpen(l.code)}>{l.name}</button>
                      <div className="sub"><span className="code">{l.code}</span> · {l.department}</div>
                    </td>
                    <td className="num">{money(l.budget)}</td>
                    <td style={{ minWidth: 150 }}>
                      <Meter value={Math.min(100, l.used_pct)} kind={l.status} tick={s.elapsed_pct}
                        label={`${l.used_pct}%`} />
                    </td>
                    <td className="num">{money(l.available)}</td>
                    <td className="num">{money(l.projected)}</td>
                    <td>
                      <Pill kind={l.status}>{l.status_label}</Pill>
                      {l.note && <div className="sub" style={{ maxWidth: 260, marginTop: 3 }}>{l.note}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="sub">The tick on each bar marks how much of the fiscal year has gone.</p>
      </section>

      <section className="sec">
        <div className="sec-head">
          <h2>Charges to check</h2>
          <span className="spacer" />
          <span className="sub">{open_anomalies.length} unreviewed</span>
        </div>
        <p className="sec-note">
          Caught by rule, not by judgment: the same vendor and amount twice within ten days, or one
          charge over a quarter of its line. Holding a charge marks it for the business office;
          marking it reviewed stops it being raised again.
        </p>
        {found.loading && <Loading what="charges" />}
        {found.data && (
          <div className="panelbox queue">
            {open_anomalies.length === 0 && <div className="qempty">Nothing unreviewed.</div>}
            {open_anomalies.map((a) => (
              <div className="qrow" key={`${a.rule}-${a.transaction_id}`} style={{ ['--sev' as string]: 'var(--serious)' }}>
                <div className="qbody">
                  <div className="qtitle">{a.vendor} · {money(a.amount, true)}</div>
                  <div className="qmeta">{a.detail}</div>
                  <div className="sub" style={{ marginTop: 3 }}>{a.rule} · #{a.transaction_id} · <span className="code">{a.line}</span> · {a.posted_on}</div>
                </div>
                <button className="btn sm primary" onClick={() => void review(a.transaction_id, 'flagged', `${a.rule}: ${a.detail}`)}>Hold for review</button>
                <button className="btn sm ghost" onClick={() => void review(a.transaction_id, 'cleared', 'Reviewed and correct.')}>Mark reviewed</button>
              </div>
            ))}
          </div>
        )}

        {held.data && held.data.length > 0 && (
          <>
            <div className="eyebrow" style={{ margin: '16px 0 8px' }}>Held for review</div>
            <div className="panelbox queue">
              {held.data.map((t) => (
                <div className="qrow" key={t.id} style={{ ['--sev' as string]: 'var(--critical)' }}>
                  <div className="qbody">
                    <div className="qtitle">{t.vendor} · {money(t.amount, true)}</div>
                    <div className="qmeta">{t.review_note || t.description}</div>
                    <div className="sub" style={{ marginTop: 3 }}>#{t.id} · <span className="code">{t.line}</span> · {t.posted_on} · {t.reference}</div>
                  </div>
                  <button className="btn sm ghost" onClick={() => void review(t.id, 'cleared', 'Reviewed and correct.')}>Resolve</button>
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      {open && lines.data && (
        <LineDrawer code={open} lines={lines.data} onClose={() => setOpen(null)} onChanged={bump} />
      )}
    </>
  )
}
