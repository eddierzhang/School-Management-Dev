import { useMemo, useState } from 'react'
import { api } from '../api'
import { useApi } from '../useApi'
import { RankedBars, TipRows } from '../components/charts'
import { ErrorNote, Loading, Meter, gradeStatus, pctText } from '../components/ui'

export function SkillGaps() {
  const { data, error, loading, reload } = useApi(() => api.skillGaps(80), [])
  const [dept, setDept] = useState('')

  const depts = useMemo(() => Array.from(new Set((data ?? []).map((g) => g.dept))).sort(), [data])
  const rows = (data ?? []).filter((g) => !dept || g.dept === dept)

  return (
    <section className="sec">
      <div className="sec-head">
        <h2>What students are struggling on</h2>
        <span className="spacer" />
        <span className="sub">{rows.length} strands</span>
      </div>
      <p className="sec-note">
        Every graded piece is tagged with the strand it tests, so mastery rolls up per topic rather
        than per class. That is the difference between "behind in maths" and "behind on word problems
        while fine on graphing" — the first is a shrug, the second is a lesson plan.
      </p>

      <div className="filters">
        <div className="field">
          <label htmlFor="sg-dept">Department</label>
          <select id="sg-dept" className="inp" value={dept} onChange={(e) => setDept(e.target.value)}>
            <option value="">Every department</option>
            {depts.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
      </div>

      {loading && <Loading what="strands" />}
      {error && <ErrorNote error={error} onRetry={reload} />}
      {rows.length > 0 && (
        <>
          <div className="chartcard" style={{ marginBottom: 16 }}>
            <div className="chart-title">Weakest twelve strands</div>
            <div className="chart-sub">Cohort mean for the strand. Anything under 72% is below the support line.</div>
            <div className="chart-scroll">
              <RankedBars
                ariaLabel="Weakest strands by cohort mean"
                labelWidth={240}
                rows={rows.slice(0, 12).map((g) => ({
                  key: g.course_code + g.skill,
                  label: `${g.skill} · ${g.course_code}`,
                  value: g.class_mean,
                  status: gradeStatus(g.class_mean),
                  tip: <TipRows title={g.skill} rows={[
                    ['Class', `${g.course_code} ${g.course_title}`],
                    ['Teacher', g.teacher],
                    ['Class average', pctText(g.class_mean)],
                    ['Below the line', `${g.students_below} of ${g.cohort}`],
                  ]} />,
                }))}
              />
            </div>
          </div>

          <div className="tblwrap">
            <table className="tbl">
              <caption className="visually-hidden">Every strand with its cohort mean and how many students are below the line</caption>
              <thead>
                <tr>
                  <th scope="col">Strand</th>
                  <th scope="col">Class</th>
                  <th scope="col">Teacher</th>
                  <th scope="col">Class average</th>
                  <th scope="col" className="num">Below line</th>
                  <th scope="col">Reading</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((g) => (
                  <tr key={g.course_code + g.skill}>
                    <td style={{ fontWeight: 600 }}>{g.skill}</td>
                    <td className="nowrap">
                      <span className="code">{g.course_code}</span>
                      <div className="sub">{g.course_title}</div>
                    </td>
                    <td className="nowrap sub">{g.teacher}</td>
                    <td style={{ minWidth: 130 }}>
                      <Meter value={g.class_mean} kind={gradeStatus(g.class_mean)} label={pctText(g.class_mean)} />
                    </td>
                    <td className="num">{g.students_below} / {g.cohort}</td>
                    <td className="sub">
                      {g.share_below >= 0.4 ? 'Reteach to the class' : g.share_below > 0 ? 'Individual referrals' : 'Holding'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
