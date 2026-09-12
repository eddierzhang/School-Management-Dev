import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError } from '../api'
import { useApi } from '../useApi'
import type { InventoryDetail, InventoryRow, StockStatus } from '../types'
import { ErrorNote, Icon, Loading, Meter, Pill, Stat } from '../components/ui'

const money = (n: number) =>
  '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const plural = (n: number, one: string, many?: string) =>
  `${n} ${n === 1 ? one : many ?? one + 's'}`

/** Meter fill carries severity; the tick marks where the reorder point sits. */
function StockMeter({ item }: { item: InventoryRow }) {
  return (
    <Meter
      value={item.ratio * 100}
      kind={item.status}
      tick={item.par > 0 ? (item.reorder_point / item.par) * 100 : undefined}
      label={`${item.on_hand} / ${item.par}`}
    />
  )
}

function ItemDrawer({ sku, onClose, onChanged }: {
  sku: string; onClose: () => void; onChanged: () => void
}) {
  const { data, error, loading, reload } = useApi(() => api.item(sku), [sku])
  const [count, setCount] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)

  useEffect(() => { if (data) setCount(String(data.on_hand)) }, [data?.sku])

  async function run(fn: () => Promise<InventoryDetail>, message: string) {
    setBusy(true); setProblem(null); setNote(null)
    try {
      await fn()
      setNote(message)
      reload()
      onChanged()
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : 'That change did not save.')
    } finally { setBusy(false) }
  }

  const step = (field: 'reorder_point' | 'par', by: number) => {
    if (!data) return
    const next = Math.max(field === 'par' ? 1 : 0, data[field] + by)
    void run(() => api.patchItem(sku, { [field]: next }), `${field === 'par' ? 'Par level' : 'Reorder point'} set to ${next}.`)
  }

  return (
    <>
      <button className="scrim" onClick={onClose} aria-label="Close item" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="item-title">
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id="item-title">{data?.name ?? sku}</h2>
            <div className="sub" style={{ marginTop: 3 }}>
              <span className="code">{sku}</span>
              {data && <> · {data.category} · {data.location}</>}
            </div>
          </div>
          <button className="btn sm ghost" onClick={onClose}>Close</button>
        </div>

        <div className="drawer-body">
          {loading && <Loading what="the item" />}
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
                <StockMeter item={data} />
                <dl className="kv">
                  <dt>On hand</dt><dd>{plural(data.on_hand, data.unit)}</dd>
                  <dt>Short of par</dt>
                  <dd>{data.short_by > 0 ? `${data.short_by} (${money(data.cost_to_par)})` : 'at par'}</dd>
                  <dt>Supplier</dt><dd>{data.supplier}</dd>
                  <dt>Unit cost</dt><dd>{money(data.unit_cost)}</dd>
                  <dt>Value on hand</dt><dd>{money(data.value_on_hand)}</dd>
                  <dt>Last counted</dt>
                  <dd>
                    {data.last_counted ?? 'never'}
                    {data.days_since_count !== null && data.days_since_count > 0 && (
                      <span className="sub"> · {data.days_since_count}d ago</span>
                    )}
                  </dd>
                </dl>
              </div>

              <div className="block">
                <h3>Physical count</h3>
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
                  <div className="field" style={{ flex: 1, minWidth: 130 }}>
                    <label htmlFor="count-in">Counted on the shelf</label>
                    <input id="count-in" className="inp" type="number" min={0} value={count}
                      onChange={(e) => setCount(e.target.value)} />
                  </div>
                  <button className="btn primary" disabled={busy || count === ''}
                    onClick={() => void run(
                      () => api.countItem(sku, Math.max(0, Number(count))),
                      `Counted: ${count} on hand.`)}>
                    Record count
                  </button>
                </div>
                <p className="sub" style={{ margin: 0 }}>
                  A count replaces the running total and stamps today's date — different from
                  nudging the number, which leaves the count date alone.
                </p>
              </div>

              <div className="block">
                <h3>Thresholds</h3>
                <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                  {([['reorder_point', 'Reorder at'], ['par', 'Par level']] as const).map(([field, label]) => (
                    <div key={field} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <span className="fact-k">{label}</span>
                      <span className="stepper">
                        <button onClick={() => step(field, -1)} disabled={busy} aria-label={`Lower ${label}`}>–</button>
                        <span className="n">{data[field]}</span>
                        <button onClick={() => step(field, 1)} disabled={busy} aria-label={`Raise ${label}`}>+</button>
                      </span>
                    </div>
                  ))}
                </div>
                <p className="sub" style={{ margin: 0 }}>
                  The reorder point raises the flag; par is what a full shelf looks like.
                </p>
              </div>

              {data.classes.length > 0 && (
                <div className="block">
                  <h3>Classes that draw on this</h3>
                  <div className="people">
                    {data.classes.map((c) => (
                      <div className="person" key={c.code}>
                        <span className="pn">{c.title}</span>
                        <span className="sub nowrap"><span className="code">{c.code}</span> · {c.enrolled} enrolled</span>
                      </div>
                    ))}
                  </div>
                  <p className="sub" style={{ margin: 0 }}>
                    {plural(data.students_affected, 'student')} depend on this item this term.
                  </p>
                </div>
              )}
            </>
          )}
        </div>

        {data && (
          <div className="drawer-foot">
            {data.requisitioned ? (
              <button className="btn" disabled={busy}
                onClick={() => void run(() => api.patchItem(sku, { requisitioned: false }), 'Removed from the requisition.')}>
                Remove from requisition
              </button>
            ) : (
              <button className="btn primary" disabled={busy}
                onClick={() => void run(() => api.patchItem(sku, { requisitioned: true }), 'Added to the requisition.')}>
                Add {data.short_by} to requisition
              </button>
            )}
          </div>
        )}
      </aside>
    </>
  )
}

export function Stockroom() {
  const [category, setCategory] = useState('')
  const [q, setQ] = useState('')
  const [attnOnly, setAttnOnly] = useState(false)
  const [openSku, setOpenSku] = useState<string | null>(null)
  const [showRequisition, setShowRequisition] = useState(false)
  const [nonce, setNonce] = useState(0)
  const [problem, setProblem] = useState<string | null>(null)

  const bump = useCallback(() => setNonce((n) => n + 1), [])

  const summary = useApi(() => api.stockroomSummary(), [nonce])
  const items = useApi(
    () => api.inventory({ category: category || undefined, q: q || undefined, needs_attention: attnOnly || undefined }),
    [category, q, attnOnly, nonce],
  )
  const requisition = useApi(() => api.requisition(), [nonce])

  const categories = useMemo(() => summary.data?.categories ?? [], [summary.data])

  async function toggleRequisition(item: InventoryRow) {
    setProblem(null)
    try {
      await api.patchItem(item.sku, { requisitioned: !item.requisitioned })
      bump()
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : 'That change did not save.')
    }
  }

  async function requisitionAll() {
    setProblem(null)
    try {
      await api.requisitionAllLow()
      bump()
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : 'Could not build the requisition.')
    }
  }

  const s = summary.data
  const rows = items.data ?? []

  return (
    <>
      <section className="sec">
        <div className="sec-head">
          <h2>Stockroom</h2>
          <span className="spacer" />
          {s && <span className="sub">{s.items} items · {money(s.value_on_hand)} on hand</span>}
        </div>
        <p className="sec-note">
          Counts are shared: an adjustment here is what the next person sees, and what the stockroom
          agent reads. Each item is tied to the classes that consume it, so a class filling up shows
          here before it runs short. The tick on every bar marks the reorder point.
        </p>

        {problem && <ErrorNote error={problem} />}

        {s && (
          <div className="strip" style={{ marginBottom: 16 }}>
            <Stat k="Needs attention" v={s.needs_attention}
              c={s.needs_attention ? `${money(s.cost_to_par)} to bring back to par` : 'stockroom is at par'} />
            <Stat k="Below reorder" v={s.below_reorder} c={`of ${s.items} items`} />
            <Stat k="On requisition" v={s.on_requisition}
              c={requisition.data ? `${money(requisition.data.cost)} on order` : '—'} />
            <Stat k="Value on hand" v={money(s.value_on_hand)} c="at last count" />
          </div>
        )}

        {requisition.data && requisition.data.lines > 0 && (
          <div className="banner" style={{ background: 'var(--accent-wash)', border: '1px solid var(--accent)' }}>
            <Icon name="good" />
            <span style={{ flex: 1, minWidth: 200 }}>
              <b>{plural(requisition.data.lines, 'line')} on the open requisition</b>
              {' — '}{money(requisition.data.cost)} to bring every flagged item up to par.
            </span>
            <button className="btn sm" onClick={() => setShowRequisition((v) => !v)}>
              {showRequisition ? 'Hide lines' : 'Review lines'}
            </button>
          </div>
        )}

        {showRequisition && requisition.data && (
          <div className="panelbox panelbox-pad" style={{ marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
            {requisition.data.by_supplier.map((g) => (
              <div key={g.supplier}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <b style={{ fontSize: 13 }}>{g.supplier}</b>
                  <span className="spacer" />
                  <span className="sub">{money(g.cost)}</span>
                </div>
                <div className="people" style={{ marginTop: 6 }}>
                  {g.lines.map((line) => (
                    <div className="person" key={line.sku}>
                      <span className="pn">
                        {line.name}
                        <div className="sub"><span className="code">{line.sku}</span> · {line.on_hand} on hand of {line.par} at par</div>
                      </span>
                      <span className="sub nowrap">{line.short_by} × {money(line.unit_cost)}</span>
                      <button className="btn sm ghost" onClick={() => void toggleRequisition(line)}>Remove</button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="filters">
          <div className="field">
            <label htmlFor="inv-cat">Category</label>
            <select id="inv-cat" className="inp" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All categories</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="field grow">
            <label htmlFor="inv-q">Search</label>
            <input id="inv-q" className="inp" type="search" value={q}
              placeholder="Item, SKU, location, supplier or course code"
              onChange={(e) => setQ(e.target.value)} />
          </div>
          <label className="toggle" htmlFor="inv-attn">
            <input id="inv-attn" type="checkbox" checked={attnOnly}
              onChange={(e) => setAttnOnly(e.target.checked)} />
            Only items needing attention
          </label>
          {s && s.needs_attention > 0 && (
            <button className="btn" style={{ marginBottom: 7 }} onClick={() => void requisitionAll()}>
              Requisition all {s.needs_attention} low items
            </button>
          )}
        </div>

        {items.loading && <Loading what="the stockroom" />}
        {items.error && <ErrorNote error={items.error} onRetry={items.reload} />}
        {!items.loading && !items.error && (
          <div className="tblwrap">
            <table className="tbl">
              <caption className="visually-hidden">
                Stockroom items with on-hand counts, reorder points and status
              </caption>
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col">Category</th>
                  <th scope="col" className="num">On hand</th>
                  <th scope="col">Level vs par</th>
                  <th scope="col" className="num">Reorder at</th>
                  <th scope="col" className="num">Students</th>
                  <th scope="col">Counted</th>
                  <th scope="col">Status</th>
                  <th scope="col" />
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr><td colSpan={9} className="empty">No item matches those filters.</td></tr>
                )}
                {rows.map((item) => (
                  <tr key={item.sku}>
                    <td>
                      <button className="rowbtn" onClick={() => setOpenSku(item.sku)}>{item.name}</button>
                      <div className="sub">
                        <span className="code">{item.sku}</span> · {item.location}
                        {item.linked_courses.length > 0 && (
                          <> · for {item.linked_courses.map((c) => <span key={c} className="code">{c} </span>)}</>
                        )}
                      </div>
                    </td>
                    <td className="nowrap sub">{item.category}</td>
                    <td className="num">{item.on_hand}</td>
                    <td style={{ minWidth: 140 }}><StockMeter item={item} /></td>
                    <td className="num">{item.reorder_point}</td>
                    <td className="num">{item.students_affected || <span className="sub">—</span>}</td>
                    <td className="nowrap sub">
                      {item.last_counted ?? '—'}
                      {item.days_since_count !== null && item.days_since_count > 10 && (
                        <> · {item.days_since_count}d</>
                      )}
                    </td>
                    <td><Pill kind={item.status as StockStatus}>{item.status_label}</Pill></td>
                    <td className="nowrap">
                      {item.requisitioned ? (
                        <button className="btn sm ghost" onClick={() => void toggleRequisition(item)}>
                          On requisition ✓
                        </button>
                      ) : (
                        <button className="btn sm" onClick={() => void toggleRequisition(item)}>
                          Requisition
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {openSku && (
        <ItemDrawer sku={openSku} onClose={() => setOpenSku(null)} onChanged={bump} />
      )}
    </>
  )
}
