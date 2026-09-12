import { useState } from 'react'
import { api } from '../api'
import { useApi } from '../useApi'
import { Columns, RankedBars, TipRows } from '../components/charts'
import { Delta, ErrorNote, Loading, Meter, Pill, gradeStatus, pctText } from '../components/ui'

export function Classes({ onOpenStudent }: { onOpenStudent: (sid: string) => void }) {
  const [selected, setSelected] = useState<string | null>(null)
  const list = useApi(() => api.courses(), [])
  const detail = useApi(() => (selected ? api.course(selected) : Promise.resolve(null)), [selected])

  return (
    <>
      <section className="sec">
        <div className="sec-head">
          <h2>Classes, weakest first</h2>
          <span className="spacer" />
          <span className="sub">{list.data?.length ?? 0} sections</span>
        </div>
        <p className="sec-note">
          A class average hides which part of the course is going wrong. The weakest strand column
          names it, so a low average can be read as a teaching problem rather than a roster of
          struggling individuals.
        </p>

        {list.loading && <Loading what="classes" />}
        {list.error && <ErrorNote error={list.error} onRetry={list.reload} />}
        {list.data && (
          <div className="tblwrap">
            <table className="tbl">
              <caption className="visually-hidden">Classes with cohort averages and their weakest strand</caption>
              <thead>
                <tr>
                  <th scope="col">Class</th>
                  <th scope="col">Teacher</th>
                  <th scope="col">Class average</th>
                  <th scope="col" className="num">Below line</th>
                  <th scope="col" className="num">Excelling</th>
                  <th scope="col">Weakest strand</th>
                  <th scope="col" />
                </tr>
              </thead>
              <tbody>
                {list.data.map((c) => (
                  <tr key={c.code}>
                    <td>
                      <button className="rowbtn" onClick={() => setSelected(c.code)}>{c.title}</button>
                      <div className="sub"><span className="code">{c.code}</span> · {c.dept} · {c.enrolled}/{c.capacity} seats</div>
                    </td>
                    <td className="nowrap sub">{c.teacher}</td>
                    <td style={{ minWidth: 130 }}>
                      {c.class_mean === null ? <span className="sub">nothing graded</span> : (
                        <Meter value={c.class_mean} kind={gradeStatus(c.class_mean)} label={pctText(c.class_mean)} />
                      )}
                    </td>
                    <td className="num">{c.below_support || <span className="sub">—</span>}</td>
                    <td className="num">{c.excelling || <span className="sub">—</span>}</td>
                    <td className="nowrap">
                      {c.weakest_skill ? (
                        <>
                          {c.weakest_skill}{' '}
                          {c.weakest_skill_mean !== null && <b>{pctText(c.weakest_skill_mean)}</b>}
                        </>
                      ) : <span className="sub">—</span>}
                    </td>
                    <td className="nowrap"><button className="btn sm" onClick={() => setSelected(c.code)}>Open</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selected && (
        <section className="sec">
          {detail.loading && <Loading what={selected} />}
          {detail.error && <ErrorNote error={detail.error} onRetry={detail.reload} />}
          {detail.data && (
            <>
              <div className="sec-head">
                <h2>{detail.data.course.title}</h2>
                <span className="sub">
                  <span className="code">{detail.data.course.code}</span> · {detail.data.course.teacher}
                  {detail.data.course.period > 0 && <> · period {detail.data.course.period}</>} · {detail.data.course.room}
                </span>
                <span className="spacer" />
                <button className="btn sm ghost" onClick={() => setSelected(null)}>Close</button>
              </div>

              <div className="split">
                <div className="chartcard">
                  <div className="chart-title">Strand averages</div>
                  <div className="chart-sub">Where this cohort is strong and where the course itself needs another pass.</div>
                  <div className="chart-scroll">
                    <RankedBars
                      ariaLabel={`Strand averages for ${detail.data.course.code}`}
                      labelWidth={180}
                      rows={detail.data.skills.map((g) => ({
                        key: g.skill,
                        label: g.skill,
                        value: g.class_mean,
                        status: gradeStatus(g.class_mean),
                        tip: <TipRows title={g.skill} rows={[
                          ['Class average', pctText(g.class_mean)],
                          ['Below the line', `${g.students_below} of ${g.cohort}`],
                          ['Share below', pctText(g.share_below * 100)],
                        ]} />,
                      }))}
                    />
                  </div>
                </div>
                <div className="chartcard">
                  <div className="chart-title">Grade spread</div>
                  <div className="chart-sub">How the {detail.data.students.length} students in this section sit.</div>
                  <div className="chart-scroll">
                    <Columns
                      ariaLabel={`Grade distribution for ${detail.data.course.code}`}
                      rows={detail.data.distribution}
                      highlight={(label) => (label === 'Below 60' ? 'critical' : label === '60–69' ? 'serious' : label === '70–79' ? 'warning' : 'accent')}
                    />
                  </div>
                </div>
              </div>

              <div className="tblwrap" style={{ marginTop: 16 }}>
                <table className="tbl">
                  <caption className="visually-hidden">Students in {detail.data.course.code}, lowest grade first</caption>
                  <thead>
                    <tr>
                      <th scope="col">Student</th>
                      <th scope="col">Grade in class</th>
                      <th scope="col" className="num">Trend</th>
                      <th scope="col" className="num">Missing</th>
                      <th scope="col">Reading</th>
                      <th scope="col" />
                    </tr>
                  </thead>
                  <tbody>
                    {detail.data.students.map((r) => (
                      <tr key={r.sid}>
                        <td>
                          <button className="rowbtn" onClick={() => onOpenStudent(r.sid)}>{r.name}</button>
                          <div className="sub"><span className="code">{r.sid}</span> · Gr {r.grade}</div>
                        </td>
                        <td style={{ minWidth: 130 }}>
                          <Meter value={r.pct} kind={gradeStatus(r.pct)} label={pctText(r.pct)} />
                        </td>
                        <td className="num"><Delta value={r.delta} /></td>
                        <td className="num">{r.missing > 0 ? `${r.missing}/${r.graded_items}` : '—'}</td>
                        <td>
                          {r.struggle_index >= 55 ? <Pill kind="critical">needs a plan here</Pill>
                            : r.struggle_index >= 35 ? <Pill kind="serious">watch</Pill>
                            : r.excel_index >= 70 ? <Pill kind="good">excelling</Pill>
                            : <span className="sub">steady</span>}
                        </td>
                        <td className="nowrap"><button className="btn sm" onClick={() => onOpenStudent(r.sid)}>Open</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      )}
    </>
  )
}
