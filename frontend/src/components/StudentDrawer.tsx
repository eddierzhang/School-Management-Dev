import { useState } from 'react'
import { api } from '../api'
import { useApi } from '../useApi'
import type { Recommendation } from '../types'
import { RankedBars } from './charts'
import { TipRows } from './charts'
import { BandPill, Delta, ErrorNote, Icon, Loading, Meter, Pill, gradeStatus, pctText } from './ui'
import { PlanDialog } from './PlanDialog'
import { DocumentsBlock } from './Documents'
import { Timetable } from './Timetable'

export function StudentDrawer({ sid, onClose, onChanged }: {
  sid: string; onClose: () => void; onChanged?: () => void
}) {
  const { data, error, loading, reload } = useApi(() => api.student(sid), [sid])
  const [planSeed, setPlanSeed] = useState<Recommendation | undefined>()
  const [planOpen, setPlanOpen] = useState(false)

  const openPlan = (seed?: Recommendation) => { setPlanSeed(seed); setPlanOpen(true) }

  async function setStatus(id: number, status: 'completed' | 'declined' | 'active') {
    await api.updateIntervention(id, { status })
    reload()
    onChanged?.()
  }

  return (
    <>
      <button className="scrim" onClick={onClose} aria-label="Close student" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="student-title">
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id="student-title">{data?.name ?? sid}</h2>
            <div className="sub" style={{ marginTop: 3 }}>
              <span className="code">{sid}</span>
              {data && <> · Grade {data.grade} · Homeroom {data.homeroom}</>}
            </div>
          </div>
          <button className="btn sm ghost" onClick={onClose}>Close</button>
        </div>

        <div className="drawer-body">
          {loading && <Loading what="the record" />}
          {error && <ErrorNote error={error} onRetry={reload} />}
          {data && (
            <>
              <div className="block">
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <BandPill band={data.band} />
                  <span className="sub">
                    struggle {data.struggle_index} · excelling {data.excel_index}
                  </span>
                </div>
                <dl className="kv">
                  <dt>Attendance</dt>
                  <dd>
                    {data.days_counted - data.absences}/{data.days_counted} days
                    {data.absences > 0 && <> · {data.absences} absent</>}
                    {data.tardies > 0 && <> · {data.tardies} late</>}
                  </dd>
                  {data.guardian_name && (
                    <>
                      <dt>Guardian</dt>
                      <dd>{data.guardian_name}{data.guardian_email && <> · {data.guardian_email}</>}</dd>
                    </>
                  )}
                </dl>
              </div>

              {data.reasons.length > 0 && (
                <div className="block">
                  <h3>Why this student is here</h3>
                  {data.reasons.map((r, i) => (
                    <div className="reason" key={`${r.code}-${i}`}>
                      <Icon name={r.kind === 'concern' ? 'critical' : 'good'} />
                      <span><b>{r.label}.</b> <span style={{ color: 'var(--ink-2)' }}>{r.detail}</span></span>
                    </div>
                  ))}
                </div>
              )}

              <DocumentsBlock sid={data.sid} name={data.name} onOpenPlan={openPlan} />

              {data.recommendations.length > 0 && (
                <div className="block">
                  <h3>What the school could do</h3>
                  {data.recommendations.map((r) => (
                    <div key={r.code + (r.course_code ?? '')} className="panelbox panelbox-pad" style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600, fontSize: 13 }}>{r.title}</div>
                        <div className="sub" style={{ marginTop: 2 }}>{r.rationale}</div>
                        <div className="sub" style={{ marginTop: 4 }}>
                          Suggested owner: {r.suggested_owner}
                          {r.course_code && <> · <span className="code">{r.course_code}</span></>}
                        </div>
                      </div>
                      <button className="btn sm primary" onClick={() => openPlan(r)}>Open a plan</button>
                    </div>
                  ))}
                </div>
              )}

              <div className="block">
                <h3>Schedule</h3>
                <Timetable sid={sid} compact />
              </div>

              <div className="block">
                <h3>Grades by class</h3>
                <table className="tbl" style={{ minWidth: 0 }}>
                  <thead>
                    <tr>
                      <th scope="col">Class</th>
                      <th scope="col" className="num">Grade</th>
                      <th scope="col" className="num">Trend</th>
                      <th scope="col" className="num">Missing</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.courses.map((c) => (
                      <tr key={c.course_code}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{c.course_title}</div>
                          <div className="sub"><span className="code">{c.course_code}</span> · {c.teacher}</div>
                          <div style={{ marginTop: 4 }}>
                            <Meter value={c.pct} kind={gradeStatus(c.pct)} label={pctText(c.pct)} />
                          </div>
                        </td>
                        <td className="num">{pctText(c.pct)}</td>
                        <td className="num"><Delta value={c.delta} /></td>
                        <td className="num">{c.missing > 0 ? `${c.missing}/${c.graded_items}` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {data.weakest_skills.length > 0 && (
                <div className="block">
                  <h3>Weakest strands</h3>
                  <RankedBars
                    ariaLabel={`Weakest skill strands for ${data.name}`}
                    labelWidth={210}
                    rows={data.weakest_skills.map((s) => ({
                      key: s.course_code + s.skill,
                      label: `${s.skill} · ${s.course_code}`,
                      value: s.pct,
                      status: gradeStatus(s.pct),
                      tip: <TipRows title={s.skill} rows={[
                        ['Class', s.course_code],
                        ['Mastery', pctText(s.pct)],
                        ['Pieces graded', String(s.graded)],
                        ['Not submitted', String(s.missing)],
                      ]} />,
                    }))}
                  />
                </div>
              )}

              {data.strongest_skills.length > 0 && (
                <div className="block">
                  <h3>Strongest strands</h3>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {data.strongest_skills.map((s) => (
                      <Pill key={s.course_code + s.skill} kind="good">
                        {s.skill} {pctText(s.pct)}
                      </Pill>
                    ))}
                  </div>
                </div>
              )}

              <div className="block">
                <h3>Support plans</h3>
                {data.interventions.length === 0 && <p className="sub" style={{ margin: 0 }}>No plan has been opened for this student.</p>}
                {data.interventions.map((iv) => (
                  <div key={iv.id} className="panelbox panelbox-pad">
                    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
                      <b style={{ fontSize: 13 }}>{iv.title}</b>
                      <Pill kind={iv.status === 'active' ? 'accent' : iv.status === 'completed' ? 'good' : 'neutral'}>
                        {iv.status}
                      </Pill>
                      <span className="spacer" />
                      {iv.status === 'active' && (
                        <>
                          <button className="btn sm" onClick={() => setStatus(iv.id, 'completed')}>Mark done</button>
                          <button className="btn sm ghost" onClick={() => setStatus(iv.id, 'declined')}>Declined</button>
                        </>
                      )}
                    </div>
                    <div className="sub" style={{ marginTop: 3 }}>
                      {iv.owner} · opened {iv.opened_on}
                      {iv.course_code && <> · <span className="code">{iv.course_code}</span></>}
                    </div>
                    {iv.rationale && <div className="sub" style={{ marginTop: 4 }}>{iv.rationale}</div>}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {data && (
          <div className="drawer-foot">
            <button className="btn primary" onClick={() => openPlan(data.recommendations[0])}>
              Open a support plan
            </button>
          </div>
        )}
      </aside>

      {planOpen && data && (
        <PlanDialog
          sid={sid} name={data.name} seed={planSeed}
          onClose={() => setPlanOpen(false)}
          onSaved={() => { reload(); onChanged?.() }}
        />
      )}
    </>
  )
}
