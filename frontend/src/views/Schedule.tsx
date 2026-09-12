import { useMemo, useState } from 'react'
import { api } from '../api'
import { useApi } from '../useApi'
import type { SectionSlot } from '../types'
import { Timetable, periodLabel } from '../components/Timetable'
import { ErrorNote, Loading, Pill, Stat } from '../components/ui'

type RowsBy = 'room' | 'teacher'

/** The master schedule for the whole school, and any one student's day. */
export function Schedule({ onOpenStudent }: { onOpenStudent: (sid: string) => void }) {
  const sched = useApi(() => api.schedule(), [])
  const students = useApi(() => api.students({ sort: 'name' }), [])
  const [rowsBy, setRowsBy] = useState<RowsBy>('room')
  const [dept, setDept] = useState('')
  const [q, setQ] = useState('')
  const [pick, setPick] = useState('')
  const [sid, setSid] = useState<string | null>(null)
  const [showAllClashes, setShowAllClashes] = useState(false)

  const s = sched.data
  const depts = useMemo(() => [...new Set((s?.sections ?? []).map((x) => x.dept))].sort(), [s])
  const visible = useMemo(() => (s?.sections ?? []).filter((x) =>
    (!dept || x.dept === dept)
    && (!q || `${x.title} ${x.code} ${x.teacher} ${x.room}`.toLowerCase().includes(q.toLowerCase()))), [s, dept, q])
  const rowKeys = useMemo(() => [...new Set(visible.map((x) => x[rowsBy]))].sort(), [visible, rowsBy])
  const cell = (key: string, period: number) => visible.filter((x) => x[rowsBy] === key && x.period === period)

  const choose = (value: string) => {
    setPick(value)
    const match = (students.data ?? []).find((st) => value === `${st.name} · ${st.sid}` || value.toUpperCase() === st.sid)
    if (match) setSid(match.sid)
  }

  const clashes = s?.student_clashes ?? []
  const shownClashes = showAllClashes ? clashes : clashes.slice(0, 8)

  return (
    <>
      <section className="sec">
        <div className="sec-head">
          <h2>School schedule</h2>
          <span className="spacer" />
          <span className="sub">{s ? `${s.sections.length} sections running` : ''}</span>
        </div>
        <p className="sec-note">
          Every section by period. Select a class to open it. Conflicts are shown, not resolved:
          a room or teacher booked twice is a timetable error, and a student enrolled in two classes
          at once is a registration error. Someone has to decide which one moves.
        </p>

        {sched.loading && <Loading what="the schedule" />}
        {sched.error && <ErrorNote error={sched.error} onRetry={sched.reload} />}

        {s && (
          <>
            <div className="strip" style={{ marginBottom: 16 }}>
              <Stat k="Sections" v={s.sections.length} c={`${new Set(s.sections.map((x) => x.base_code)).size} classes`} />
              <Stat k="Periods in use" v={new Set(s.sections.map((x) => x.period).filter((p) => p > 0)).size}
                c={`of ${s.periods.filter((p) => p > 0).length}`} />
              <Stat k="Rooms · teachers" v={`${s.rooms.length} · ${s.teachers.length}`} />
              <Stat k="Timetable clashes" v={s.clashes.length}
                c={s.clashes.length ? 'a room or teacher double-booked' : 'no room or teacher double-booked'} />
              <Stat k="Students with clashes" v={s.students_with_clashes}
                c={s.students_with_clashes ? 'enrolled in two classes at once' : 'every student can attend every class'} />
            </div>

            {s.clashes.map((c) => (
              <div key={`${c.kind}-${c.who}-${c.period}`} className="banner critical">
                <b>{c.kind === 'room' ? 'Room' : 'Teacher'} double-booked:</b>
                {c.who} in {periodLabel(c.period)} — {c.sections.join(', ')}
              </div>
            ))}

            <div className="filters">
              <div className="field">
                <label htmlFor="sc-rows">Rows</label>
                <select id="sc-rows" className="inp" value={rowsBy} onChange={(e) => setRowsBy(e.target.value as RowsBy)}>
                  <option value="room">By room</option>
                  <option value="teacher">By teacher</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="sc-dept">Department</label>
                <select id="sc-dept" className="inp" value={dept} onChange={(e) => setDept(e.target.value)}>
                  <option value="">Every department</option>
                  {depts.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
              <div className="field grow">
                <label htmlFor="sc-q">Search</label>
                <input id="sc-q" className="inp" type="search" value={q} placeholder="Class, code, teacher or room"
                  onChange={(e) => setQ(e.target.value)} />
              </div>
            </div>

            <div className="tblwrap" style={{ marginTop: 14 }}>
              <table className="tbl" style={{ tableLayout: 'fixed', minWidth: 130 + s.periods.length * 130 }}>
                <caption className="visually-hidden">Sections by {rowsBy} and period</caption>
                <colgroup>
                  <col style={{ width: 130 }} />
                  {s.periods.map((p) => <col key={p} />)}
                </colgroup>
                <thead>
                  <tr>
                    <th scope="col">{rowsBy === 'room' ? 'Room' : 'Teacher'}</th>
                    {s.periods.map((p) => <th scope="col" key={p}>{p === 0 ? 'Outside timetable' : `Period ${p}`}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {rowKeys.map((key) => (
                    <tr key={key}>
                      <th scope="row" className="nowrap" style={{ fontWeight: 600 }}>{key}</th>
                      {s.periods.map((p) => {
                        const here = cell(key, p)
                        return (
                          <td key={p} style={{ verticalAlign: 'top', padding: 6, background: here.length > 1 ? 'var(--critical-wash)' : undefined }}>
                            {here.map((x) => <SlotCard key={x.code} s={x} rowsBy={rowsBy} />)}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                  {rowKeys.length === 0 && (
                    <tr><td colSpan={s.periods.length + 1} className="sub">No sections match.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="sec">
        <div className="sec-head">
          <h2>A student's schedule</h2>
        </div>
        <div className="filters">
          <div className="field grow">
            <label htmlFor="sc-student">Student</label>
            <input id="sc-student" className="inp" list="sc-students" value={pick}
              placeholder="Type a name or student ID" onChange={(e) => choose(e.target.value)} />
            <datalist id="sc-students">
              {(students.data ?? []).map((st) => <option key={st.sid} value={`${st.name} · ${st.sid}`} />)}
            </datalist>
          </div>
          {sid && <button className="btn" onClick={() => onOpenStudent(sid)}>Open full record</button>}
        </div>
        <div style={{ marginTop: 14, maxWidth: 640 }}>
          {sid ? <Timetable sid={sid} /> : <p className="sub">Choose a student to see their day, or pick one from the clashes below.</p>}
        </div>
      </section>

      {clashes.length > 0 && (
        <section className="sec">
          <div className="sec-head">
            <h2>Students enrolled in two classes at once</h2>
            <span className="spacer" />
            <span className="sub">{s?.students_with_clashes} students · {clashes.length} clashes</span>
          </div>
          <div className="tblwrap">
            <table className="tbl">
              <caption className="visually-hidden">Students with two enrolled classes in the same period</caption>
              <thead>
                <tr>
                  <th scope="col">Student</th>
                  <th scope="col">Period</th>
                  <th scope="col">Classes at the same time</th>
                  <th scope="col" />
                </tr>
              </thead>
              <tbody>
                {shownClashes.map((c) => (
                  <tr key={`${c.sid}-${c.period}`}>
                    <td>
                      <button className="rowbtn" onClick={() => { setSid(c.sid); setPick(`${c.name} · ${c.sid}`) }}>{c.name}</button>
                      <div className="sub"><span className="code">{c.sid}</span> · Gr {c.grade}</div>
                    </td>
                    <td className="nowrap">{periodLabel(c.period)}</td>
                    <td>{c.sections.map((code) => <span key={code} className="code" style={{ marginRight: 8 }}>{code}</span>)}</td>
                    <td className="nowrap">
                      <button className="btn sm" onClick={() => { setSid(c.sid); setPick(`${c.name} · ${c.sid}`) }}>Show schedule</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {clashes.length > shownClashes.length && (
            <button className="btn sm ghost" style={{ marginTop: 8 }} onClick={() => setShowAllClashes(true)}>
              Show all {clashes.length}
            </button>
          )}
        </section>
      )}
    </>
  )
}

function SlotCard({ s, rowsBy }: { s: SectionSlot; rowsBy: RowsBy }) {
  const full = s.enrolled >= s.capacity
  return (
    <a href={`#/classes/${encodeURIComponent(s.code)}`} style={{
      display: 'block', textDecoration: 'none', color: 'inherit', background: 'var(--card-2)',
      border: '1px solid var(--rule)', borderLeft: '3px solid var(--accent)', borderRadius: 6,
      padding: '6px 8px', marginBottom: 4,
    }}>
      <div style={{ fontWeight: 600, fontSize: 12.5, lineHeight: 1.25 }}>{s.title}</div>
      <div className="sub" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        <span className="code">{s.code}</span> · {rowsBy === 'room' ? s.teacher : s.room}
      </div>
      <div className="sub">
        {s.enrolled}/{s.capacity}
        {full && !s.waitlist && ' · full'}
        {s.waitlist > 0 && <> · <Pill kind="serious">{s.waitlist} waiting</Pill></>}
      </div>
    </a>
  )
}
