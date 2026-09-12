import { useState } from 'react'
import { api } from '../api'
import { useApi } from '../useApi'
import { BandPill, Delta, ErrorNote, Loading, Meter, pctText, statusColor } from '../components/ui'

export function Watchlist({ onOpenStudent }: { onOpenStudent: (sid: string) => void }) {
  const [band, setBand] = useState('')
  const [grade, setGrade] = useState('')
  const [q, setQ] = useState('')
  const [unplannedOnly, setUnplannedOnly] = useState(false)

  const { data, error, loading, reload } = useApi(
    () => api.students({ band: band || undefined, grade: grade ? Number(grade) : undefined, q: q || undefined, sort: 'struggle' }),
    [band, grade, q],
  )

  const rows = (data ?? []).filter((r) => (!unplannedOnly || r.open_interventions === 0))

  return (
    <section className="sec">
      <div className="sec-head">
        <h2>Who is struggling</h2>
        <span className="spacer" />
        <span className="sub">{rows.length} students</span>
      </div>
      <p className="sec-note">
        The struggle index is 0.55 low mastery + 0.20 decline + 0.15 unsubmitted work + 0.10 absence,
        taken from the worst class and escalated when more than one class is affected. Open a student
        to see the arithmetic and what it suggests.
      </p>
      <div className="formula">
        struggle = worst_class + 0.35 × (100 − worst_class) × mean(other_classes) ÷ 100
      </div>

      <div className="filters" style={{ marginTop: 14 }}>
        <div className="field">
          <label htmlFor="wl-band">Band</label>
          <select id="wl-band" className="inp" value={band} onChange={(e) => setBand(e.target.value)}>
            <option value="">Every band</option>
            <option value="needs-plan">Needs a plan</option>
            <option value="watch">Watch</option>
            <option value="steady">Steady</option>
            <option value="excelling">Excelling</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="wl-grade">Grade</label>
          <select id="wl-grade" className="inp" value={grade} onChange={(e) => setGrade(e.target.value)}>
            <option value="">All grades</option>
            <option value="6">6</option><option value="7">7</option><option value="8">8</option>
          </select>
        </div>
        <div className="field grow">
          <label htmlFor="wl-q">Search</label>
          <input id="wl-q" className="inp" type="search" value={q} placeholder="Name, student ID or homeroom"
            onChange={(e) => setQ(e.target.value)} />
        </div>
        <label className="toggle" htmlFor="wl-unplanned">
          <input id="wl-unplanned" type="checkbox" checked={unplannedOnly} onChange={(e) => setUnplannedOnly(e.target.checked)} />
          Only students without a plan
        </label>
      </div>

      {loading && <Loading what="students" />}
      {error && <ErrorNote error={error} onRetry={reload} />}
      {!loading && !error && (
        <div className="tblwrap">
          <table className="tbl">
            <caption className="visually-hidden">Students ranked by struggle index with the reason and their lowest class</caption>
            <thead>
              <tr>
                <th scope="col">Student</th>
                <th scope="col">Band</th>
                <th scope="col">Struggle</th>
                <th scope="col">Why</th>
                <th scope="col">Lowest class</th>
                <th scope="col" className="num">Absent</th>
                <th scope="col" className="num">Plans</th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={8} className="empty">No student matches those filters.</td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.sid}>
                  <td>
                    <button className="rowbtn" onClick={() => onOpenStudent(r.sid)}>{r.name}</button>
                    <div className="sub"><span className="code">{r.sid}</span> · Gr {r.grade} · {r.homeroom}</div>
                  </td>
                  <td><BandPill band={r.band} /></td>
                  <td style={{ minWidth: 120 }}>
                    <Meter
                      value={r.struggle_index}
                      kind={r.struggle_index >= 55 ? 'critical' : r.struggle_index >= 35 ? 'serious' : 'neutral'}
                      label={String(r.struggle_index)}
                    />
                    {r.excel_index >= 60 && (
                      <div className="sub" style={{ marginTop: 3, color: statusColor('good') }}>
                        also excelling ({r.excel_index})
                      </div>
                    )}
                  </td>
                  <td style={{ fontSize: 12.5, maxWidth: 260 }}>{r.top_reason ?? <span className="sub">—</span>}</td>
                  <td className="nowrap">
                    {r.lowest_course ? (
                      <>
                        <span className="code">{r.lowest_course}</span>{' '}
                        {r.lowest_pct !== null && <b>{pctText(r.lowest_pct)}</b>}
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

export function Strengths({ onOpenStudent }: { onOpenStudent: (sid: string) => void }) {
  const { data, error, loading, reload } = useApi(() => api.strengths(30), [])

  return (
    <section className="sec">
      <div className="sec-head">
        <h2>Who is excelling</h2>
        <span className="spacer" />
        <span className="sub">{data?.length ?? 0} students</span>
      </div>
      <p className="sec-note">
        Deliberately not the inverse of the watchlist. A student can be failing maths and top of the
        class in science, and that student appears on both lists — the second is where the school
        finds the lever. Enrichment suggestions prefer a class in the same department with room in it.
      </p>

      {loading && <Loading what="strengths" />}
      {error && <ErrorNote error={error} onRetry={reload} />}
      <div className="cards">
        {data?.map((st) => {
          const best = st.courses.reduce((a, b) => (b.excel_index > a.excel_index ? b : a), st.courses[0]!)
          const enrich = st.recommendations.find((r) => r.kind === 'enrichment')
          const alsoStruggling = st.struggle_index >= 35
          return (
            <article className="icard" key={st.sid}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <button className="rowbtn" style={{ fontSize: 14.5 }} onClick={() => onOpenStudent(st.sid)}>{st.name}</button>
                  <div className="sub">Gr {st.grade} · {st.homeroom}</div>
                </div>
                <span className="pill good">excelling {st.excel_index}</span>
              </div>
              {best && (
                <div style={{ fontSize: 12.5 }}>
                  Strongest in <b>{best.course_title}</b> at {pctText(best.pct)}{' '}
                  <Delta value={best.delta} />
                </div>
              )}
              {st.strongest_skills.length > 0 && (
                <div className="sub">Best strands: {st.strongest_skills.slice(0, 2).map((s) => s.skill).join(', ')}</div>
              )}
              {alsoStruggling && (
                <div className="sub" style={{ color: 'var(--critical)' }}>
                  Also flagged: struggle {st.struggle_index} in {st.courses[0]?.course_code}
                </div>
              )}
              {enrich && (
                <div className="panelbox panelbox-pad" style={{ padding: '10px 12px' }}>
                  <div style={{ fontWeight: 600, fontSize: 12.5 }}>{enrich.title}</div>
                  <div className="sub" style={{ marginTop: 2 }}>{enrich.rationale}</div>
                </div>
              )}
              <div style={{ marginTop: 'auto', paddingTop: 4 }}>
                <button className="btn sm" onClick={() => onOpenStudent(st.sid)}>Open record</button>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
