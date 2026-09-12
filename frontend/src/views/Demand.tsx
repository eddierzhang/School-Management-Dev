import { useEffect, useMemo, useState } from 'react'
import { api, ApiError } from '../api'
import { useApi } from '../useApi'
import type { ClassDemand, DemandAction } from '../types'
import { RankedBars, TipRows } from '../components/charts'
import { ErrorNote, Icon, Loading, Meter, Pill, Stat, pctText } from '../components/ui'

const ACTION: Record<DemandAction, { label: string; detail: string } | null> = {
  'open-section': { label: 'Open a section', detail: 'The waitlist would fill much of another section' },
  'raise-capacity': { label: 'Add seats', detail: 'A short waitlist — a few more seats may clear it' },
  promote: { label: 'Promote it', detail: 'Seats to fill — a bulletin or homeroom slide' },
  review: { label: 'Review for next term', detail: 'Under-filled and signups are cooling' },
  none: null,
}

type Opening = { mode: 'class' } | { mode: 'section'; target: ClassDemand }

/** Which classes students want, which they don't, and opening more of either kind. */
export function Demand({ onChanged }: { onChanged: () => void }) {
  const report = useApi(() => api.demand(), [])
  const [opening, setOpening] = useState<Opening | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const classes = report.data?.classes ?? []

  const over = classes.filter((c) => c.label === 'Over-subscribed')
  const toFill = classes.filter((c) => c.label === 'Seats to fill')
  const waiting = classes.reduce((a, c) => a + c.waitlist, 0)
  const sections = classes.reduce((a, c) => a + c.sections.length, 0)

  function opened(message: string) {
    setNotice(message)
    report.reload()
    onChanged()
  }

  return (
    <>
      <section className="sec">
        <div className="sec-head">
          <h2>Class demand</h2>
          <span className="spacer" />
          <button className="btn primary" onClick={() => setOpening({ mode: 'class' })}>New class</button>
        </div>
        <p className="sec-note">
          Popularity is judged per class, with every section pooled: once a second section takes
          the waitlist, the class reads as relieved rather than one full section and one empty one.
          The index is the registrar console's, so both halves rank classes the same way.
        </p>

        {report.loading && <Loading what="demand" />}
        {report.error && <ErrorNote error={report.error} onRetry={report.reload} />}
        {notice && (
          <div className="banner" style={{ background: 'var(--accent-wash)', border: '1px solid var(--accent)' }}>
            <Icon name="good" />
            <span style={{ flex: 1, minWidth: 200 }}>{notice}</span>
            <button className="btn sm ghost" onClick={() => setNotice(null)}>Dismiss</button>
          </div>
        )}

        {report.data && (
          <>
            <div className="strip" style={{ marginBottom: 16 }}>
              <Stat k="Over-subscribed" v={over.length}
                c={over.length ? over.slice(0, 3).map((c) => c.code).join(', ') : 'no class is turning students away'} />
              <Stat k="Students waiting" v={waiting} c={`across ${classes.filter((c) => c.waitlist).length} classes`} />
              <Stat k="Seats to fill" v={toFill.length}
                c={toFill.length ? toFill.map((c) => c.code).join(', ') : 'every class is drawing students'} />
              <Stat k="Sections" v={sections} c={`${classes.length} classes`} />
            </div>

            <div className="chartcard">
              <div className="chart-title">Demand index, most wanted first</div>
              <div className="chart-sub">
                Colour is the band. Select a class with a waitlist to open another section of it.
              </div>
              <div className="chart-scroll">
                <RankedBars
                  ariaLabel="Demand index by class, ranked"
                  labelWidth={220}
                  rows={classes.map((c) => ({
                    key: c.code,
                    label: c.title,
                    value: c.score,
                    status: c.kind,
                    onSelect: c.waitlist ? () => setOpening({ mode: 'section', target: c }) : undefined,
                    tip: <TipRows title={`${c.title} · ${c.label}`} rows={[
                      ['Demand index', String(c.score)],
                      ['Seats filled', `${c.enrolled} of ${c.capacity}`],
                      ['Waiting', String(c.waitlist)],
                      ['Signups, last 2 wk', `${c.recent_signups} (was ${c.prior_signups})`],
                    ]} />,
                  }))}
                />
              </div>
            </div>
          </>
        )}
      </section>

      {report.data && (
        <section className="sec">
          <div className="sec-head"><h2>Every class</h2></div>
          <div className="tblwrap">
            <table className="tbl">
              <caption className="visually-hidden">Classes with seats filled, waitlist, recent signups, demand index and suggested action</caption>
              <thead>
                <tr>
                  <th scope="col">Class</th>
                  <th scope="col">Seats filled</th>
                  <th scope="col" className="num">Waiting</th>
                  <th scope="col" className="num">Signups, 2 wk</th>
                  <th scope="col">Demand</th>
                  <th scope="col">What to do</th>
                </tr>
              </thead>
              <tbody>
                {classes.map((c) => {
                  const act = ACTION[c.action]
                  return (
                    <tr key={c.code}>
                      <td>
                        <b>{c.title}</b>
                        <div className="sub">
                          <span className="code">{c.code}</span> · {c.dept} ·{' '}
                          {c.sections.length === 1 ? '1 section' : `${c.sections.length} sections (${c.sections.map((s) => s.code).join(', ')})`}
                        </div>
                      </td>
                      <td style={{ minWidth: 150 }}>
                        <Meter value={c.fill * 100} kind={c.fill < 0.55 ? 'warning' : 'accent'}
                          label={`${c.enrolled}/${c.capacity}`} />
                      </td>
                      <td className="num">{c.waitlist || <span className="sub">—</span>}</td>
                      <td className="num nowrap">
                        {c.recent_signups}{' '}
                        <span className="sub" title={`${c.prior_signups} in the two weeks before`}
                          style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                          {c.trend !== 'level' && <Icon name={c.trend} />}
                          {c.trend === 'level' ? 'level' : `from ${c.prior_signups}`}
                        </span>
                      </td>
                      <td className="nowrap"><b>{c.score}</b> <Pill kind={c.kind}>{c.label}</Pill></td>
                      <td>
                        {act ? (
                          <>
                            {c.action === 'open-section' ? (
                              <button className="btn sm primary" onClick={() => setOpening({ mode: 'section', target: c })}>
                                Open a section
                              </button>
                            ) : (
                              <span className="nowrap">
                                <b style={{ fontSize: 12.5 }}>{act.label}</b>
                                {c.waitlist > 0 && (
                                  <button className="btn sm ghost" onClick={() => setOpening({ mode: 'section', target: c })}>
                                    or open a section
                                  </button>
                                )}
                              </span>
                            )}
                            <div className="sub">{c.reasons[0]}{c.action === 'open-section' ? '' : ` · ${act.detail.toLowerCase()}`}</div>
                          </>
                        ) : <span className="sub">{c.reasons[0]}</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="formula" style={{ marginTop: 14 }}>{report.data.formula}</div>
          <p className="sub" style={{ marginTop: 8 }}>
            Each term is capped at 1, so a huge waitlist cannot swamp the other signals.{' '}
            {report.data.bands.map((b) => `${b.label} ${b.min}+`).join(' · ')}.
          </p>
        </section>
      )}

      {opening && (
        <OpenDialog
          opening={opening}
          depts={[...new Set(classes.map((c) => c.dept))].sort()}
          onClose={() => setOpening(null)}
          onOpened={opened}
        />
      )}
    </>
  )
}

const PERIODS = [1, 2, 3, 4, 5, 6, 7, 8]

function OpenDialog({ opening, depts, onClose, onOpened }: {
  opening: Opening
  depts: string[]
  onClose: () => void
  onOpened: (message: string) => void
}) {
  const target = opening.mode === 'section' ? opening.target : null
  const first = target?.sections[0]
  const largest = target ? Math.max(...target.sections.map((s) => s.capacity)) : 20
  const [period, setPeriod] = useState(first?.period ? (first.period % 8) + 1 : 1)
  const [room, setRoom] = useState('')
  const [teacher, setTeacher] = useState('')
  const [capacity, setCapacity] = useState(largest)
  const [move, setMove] = useState(target ? Math.min(target.waitlist, largest) : 0)
  const [code, setCode] = useState('')
  const [title, setTitle] = useState('')
  const [dept, setDept] = useState('')
  const [length, setLength] = useState<'year' | 'semester'>('semester')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const free = useApi(() => api.openings(period), [period])

  // Suggest the first free room once a period's openings arrive, without overwriting a typed one.
  useEffect(() => {
    if (free.data && (!room || !free.data.free_rooms.includes(room))) setRoom(free.data.free_rooms[0] ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [free.data])

  const busyTeacher = useMemo(() => {
    const t = (teacher || first?.teacher || '').trim()
    return !!(t && free.data && !free.data.free_teachers.includes(t))
  }, [teacher, first, free.data])

  const valid = room.trim() && capacity >= 1 && (target
    ? true
    : /^[A-Za-z]{2,4}-\d{3}$/.test(code.trim()) && title.trim().length >= 3 && dept.trim().length >= 2 && teacher.trim().length >= 2)

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const res = target
        ? await api.openSection(first?.code ?? target.code, {
            period, room: room.trim(), teacher: teacher.trim() || null, capacity,
            move_from_waitlist: Math.min(move, capacity),
          })
        : await api.openClass({
            code: code.trim(), title: title.trim(), dept: dept.trim(), teacher: teacher.trim(), period,
            room: room.trim(), capacity, description: description.trim(), length,
            credits: length === 'year' ? 1 : 0.5,
          })
      onOpened(res.message)
      onClose()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The class could not be opened.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <button className="scrim" style={{ zIndex: 60 }} onClick={onClose} aria-label="Cancel" />
      <aside className="drawer" style={{ zIndex: 70, width: 'min(460px, 100%)' }} role="dialog" aria-modal="true" aria-labelledby="open-title">
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id="open-title">{target ? `Open a section of ${target.title}` : 'Open a new class'}</h2>
            <div className="sub" style={{ marginTop: 3 }}>
              {target ? (
                <><span className="code">{target.code}</span> · {target.enrolled}/{target.capacity} seats · {target.waitlist} waiting · demand {target.score}</>
              ) : 'Starts with no students; it will read as seats to fill until signups arrive.'}
            </div>
          </div>
          <button className="btn sm ghost" onClick={onClose}>Close</button>
        </div>
        <div className="drawer-body">
          {error && <ErrorNote error={error} />}

          {!target && (
            <>
              <div className="field">
                <label htmlFor="oc-code">Course code</label>
                <input id="oc-code" className="inp" value={code} placeholder="ART-155"
                  onChange={(e) => setCode(e.target.value.toUpperCase())} />
              </div>
              <div className="field">
                <label htmlFor="oc-title">Title</label>
                <input id="oc-title" className="inp" value={title} placeholder="Printmaking" onChange={(e) => setTitle(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="oc-dept">Department</label>
                <input id="oc-dept" className="inp" list="oc-depts" value={dept} onChange={(e) => setDept(e.target.value)} />
                <datalist id="oc-depts">{depts.map((d) => <option key={d} value={d} />)}</datalist>
              </div>
              <div className="field">
                <label htmlFor="oc-length">Length</label>
                <select id="oc-length" className="inp" value={length} onChange={(e) => setLength(e.target.value as 'year' | 'semester')}>
                  <option value="semester">One semester · 0.5 credits</option>
                  <option value="year">Full year · 1 credit</option>
                </select>
              </div>
            </>
          )}

          <div className="field">
            <label htmlFor="oc-period">Period</label>
            <select id="oc-period" className="inp" value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
              {PERIODS.map((p) => <option key={p} value={p}>Period {p}</option>)}
              <option value={0}>Outside the timetable</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="oc-room">Room</label>
            <input id="oc-room" className="inp" list="oc-rooms" value={room} onChange={(e) => setRoom(e.target.value)} />
            <datalist id="oc-rooms">{free.data?.free_rooms.map((r) => <option key={r} value={r} />)}</datalist>
            <span className="sub">
              {free.data ? `${free.data.free_rooms.length} rooms free in ${period ? `period ${period}` : 'this slot'}` : 'Checking rooms…'}
            </span>
          </div>
          <div className="field">
            <label htmlFor="oc-teacher">Teacher</label>
            <input id="oc-teacher" className="inp" list="oc-teachers" value={teacher}
              placeholder={first?.teacher ?? 'R. Okonkwo'} onChange={(e) => setTeacher(e.target.value)} />
            <datalist id="oc-teachers">{free.data?.free_teachers.map((t) => <option key={t} value={t} />)}</datalist>
            {busyTeacher && <span className="sub" style={{ color: 'var(--critical)' }}>Already teaching in this period — pick another period or teacher.</span>}
          </div>
          <div className="field">
            <label htmlFor="oc-cap">Seats</label>
            <input id="oc-cap" className="inp" type="number" min={1} max={120} value={capacity}
              onChange={(e) => setCapacity(Math.max(1, Number(e.target.value) || 1))} />
          </div>

          {target ? (
            <div className="field">
              <label htmlFor="oc-move">Move from the waitlist</label>
              <input id="oc-move" className="inp" type="number" min={0} max={Math.min(target.waitlist, capacity)} value={move}
                onChange={(e) => setMove(Math.max(0, Math.min(target.waitlist, Number(e.target.value) || 0)))} />
              <span className="sub">
                In the order students joined it. {target.waitlist} waiting; moving {Math.min(move, capacity)} leaves{' '}
                {target.waitlist - Math.min(move, capacity)} and fills {pctText((100 * Math.min(move, capacity)) / capacity)} of the new section.
              </span>
            </div>
          ) : (
            <div className="field">
              <label htmlFor="oc-desc">Description</label>
              <textarea id="oc-desc" className="inp" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
          )}
        </div>
        <div className="drawer-foot">
          <button className="btn primary" disabled={saving || !valid || busyTeacher} onClick={save}>
            {saving ? 'Opening…' : target ? 'Open the section' : 'Open the class'}
          </button>
          <button className="btn ghost" onClick={onClose}>Cancel</button>
        </div>
      </aside>
    </>
  )
}
