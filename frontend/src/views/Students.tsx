import { useMemo, useState } from 'react'
import { api } from '../api'
import { useApi } from '../useApi'
import type { StudentRow } from '../types'
import { BandPill, ErrorNote, Loading, StandingMeter, pctText } from '../components/ui'

/* One list for every student. The struggling and excelling lists used to be
   separate tabs, which left steady students with no view at all — nobody was
   watching the ones in the middle until they slid into a band. */

export type Group = 'all' | 'concern' | 'needs-plan' | 'watch' | 'steady' | 'excelling' | 'strength' | 'mixed'

const GROUPS: { id: Group; label: string; test: (r: StudentRow) => boolean }[] = [
  { id: 'all', label: 'All students', test: () => true },
  { id: 'concern', label: 'Struggling', test: (r) => r.band === 'needs-plan' || r.band === 'watch' },
  { id: 'needs-plan', label: 'Needs a plan', test: (r) => r.band === 'needs-plan' },
  { id: 'watch', label: 'Watch', test: (r) => r.band === 'watch' },
  { id: 'steady', label: 'Steady', test: (r) => r.band === 'steady' },
  { id: 'excelling', label: 'Excelling', test: (r) => r.band === 'excelling' },
  // Not the same as the excelling band: a student can be on a plan in maths and
  // top of the class in science, and the second fact is where the lever is.
  { id: 'strength', label: 'Has a strength', test: (r) => r.excel_index >= 60 },
  { id: 'mixed', label: 'Mixed', test: (r) => r.mixed },
]

const SORTS: Record<string, (a: StudentRow, b: StudentRow) => number> = {
  low: (a, b) => a.standing - b.standing || a.name.localeCompare(b.name),
  high: (a, b) => b.standing - a.standing || a.name.localeCompare(b.name),
  name: (a, b) => a.name.localeCompare(b.name),
  grade: (a, b) => a.grade - b.grade || a.name.localeCompare(b.name),
}

export function Students({ onOpenStudent, group, onGroup, refresh = 0 }: {
  onOpenStudent: (sid: string) => void
  group: Group
  onGroup: (g: Group) => void
  refresh?: number
}) {
  const [grade, setGrade] = useState('')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState(group === 'excelling' || group === 'strength' ? 'high' : 'low')
  const [unplannedOnly, setUnplannedOnly] = useState(false)

  // Fetch everyone once and filter here, so every group's count stays visible
  // whichever group is selected. Refetching on refresh (rather than remounting)
  // keeps the filters when a plan is opened from the drawer.
  const { data, error, loading, reload } = useApi(() => api.students({ sort: 'standing' }), [refresh])

  const base = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return (data ?? []).filter((r) =>
      (!grade || r.grade === Number(grade))
      && (!needle || r.name.toLowerCase().includes(needle) || r.sid.toLowerCase().includes(needle)
        || r.homeroom.toLowerCase().includes(needle))
      && (!unplannedOnly || r.open_interventions === 0))
  }, [data, grade, q, unplannedOnly])

  const active = GROUPS.find((g) => g.id === group) ?? GROUPS[0]!
  const rows = base.filter(active.test).sort(SORTS[sort])

  return (
    <section className="sec">
      <div className="sec-head">
        <h2>Students</h2>
        <span className="spacer" />
        <span className="sub">{rows.length} of {data?.length ?? 0} students</span>
      </div>
      <p className="sec-note">
        Every student in the school, struggling, steady or excelling. Standing is one number from
        −100 to +100: the excelling index minus the struggle index. Because it nets the two, a student
        failing one class and top of another can land near zero, so they are marked <b>mixed</b>.
        Bands still come from the struggle index first. Open a student to see both indices and what
        they suggest.
      </p>

      <div className="groupbar" role="group" aria-label="Show students">
        {GROUPS.map((g) => (
          <button key={g.id} className="groupbtn" aria-pressed={group === g.id} onClick={() => onGroup(g.id)}>
            {g.label}
            <span className="count">{data ? base.filter(g.test).length : '—'}</span>
          </button>
        ))}
      </div>

      <div className="filters">
        <div className="field">
          <label htmlFor="st-grade">Grade</label>
          <select id="st-grade" className="inp" value={grade} onChange={(e) => setGrade(e.target.value)}>
            <option value="">All grades</option>
            <option value="9">9</option><option value="10">10</option><option value="11">11</option><option value="12">12</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="st-sort">Sort</label>
          <select id="st-sort" className="inp" value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="low">Lowest standing first</option>
            <option value="high">Highest standing first</option>
            <option value="name">Name</option>
            <option value="grade">Grade</option>
          </select>
        </div>
        <div className="field grow">
          <label htmlFor="st-q">Search</label>
          <input id="st-q" className="inp" type="search" value={q} placeholder="Name, student ID or homeroom"
            onChange={(e) => setQ(e.target.value)} />
        </div>
        <label className="toggle" htmlFor="st-unplanned">
          <input id="st-unplanned" type="checkbox" checked={unplannedOnly} onChange={(e) => setUnplannedOnly(e.target.checked)} />
          Only students without a plan
        </label>
      </div>

      {loading && <Loading what="students" />}
      {error && <ErrorNote error={error} onRetry={reload} />}
      {!loading && !error && (
        <div className="tblwrap">
          <table className="tbl">
            <caption className="visually-hidden">Every student with their band, standing score, and their lowest and strongest class</caption>
            <thead>
              <tr>
                <th scope="col">Student</th>
                <th scope="col">Band</th>
                <th scope="col">Standing</th>
                <th scope="col">Why</th>
                <th scope="col">Lowest class</th>
                <th scope="col">Strongest class</th>
                <th scope="col" className="num">Absent</th>
                <th scope="col" className="num">Plans</th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={9} className="empty">No student matches those filters.</td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.sid}>
                  <td>
                    <button className="rowbtn" onClick={() => onOpenStudent(r.sid)}>{r.name}</button>
                    <div className="sub"><span className="code">{r.sid}</span> · Gr {r.grade} · {r.homeroom}</div>
                  </td>
                  <td><BandPill band={r.band} /></td>
                  <td style={{ minWidth: 150 }}>
                    <StandingMeter value={r.standing} mixed={r.mixed} />
                  </td>
                  <td style={{ fontSize: 12.5, maxWidth: 240 }}>{r.top_reason ?? <span className="sub">—</span>}</td>
                  <td className="nowrap">
                    {r.lowest_course ? (
                      <>
                        <span className="code">{r.lowest_course}</span>{' '}
                        {r.lowest_pct !== null && <b>{pctText(r.lowest_pct)}</b>}
                      </>
                    ) : <span className="sub">—</span>}
                  </td>
                  <td className="nowrap">
                    {r.strongest_course ? (
                      <>
                        <span className="code">{r.strongest_course}</span>{' '}
                        {r.strongest_pct !== null && <b>{pctText(r.strongest_pct)}</b>}
                      </>
                    ) : <span className="sub">—</span>}
                  </td>
                  <td className="num">{r.absence_rate > 0 ? pctText(r.absence_rate * 100) : '—'}</td>
                  <td className="num">{r.open_interventions || <span className="sub">none</span>}</td>
                  <td className="nowrap"><button className="btn sm" onClick={() => onOpenStudent(r.sid)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
