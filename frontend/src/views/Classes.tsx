import { api } from '../api'
import { useAuth } from '../auth'
import { useApi } from '../useApi'
import type { CourseAssessmentRow, CourseDetail } from '../types'
import { Columns, RankedBars, TipRows, useTooltip } from '../components/charts'
import { ClassPlans } from '../components/ClassPlans'
import { Delta, ErrorNote, Loading, Meter, Pill, Stat, gradeStatus, pctText } from '../components/ui'

/** The list when no class is open; the class's own page when one is. The open
    class lives in the URL (#/classes/MAT-150), so a page can be bookmarked or sent. */
export function Classes({ code, onOpenClass, onOpenStudent }: {
  code: string | null
  onOpenClass: (code: string | null) => void
  onOpenStudent: (sid: string) => void
}) {
  if (code) return <ClassPage code={code} onBack={() => onOpenClass(null)} onOpenClass={onOpenClass} onOpenStudent={onOpenStudent} />
  return <ClassList onOpenClass={onOpenClass} />
}

function ClassList({ onOpenClass }: { onOpenClass: (code: string) => void }) {
  const list = useApi(() => api.courses(), [])
  return (
    <section className="sec">
      <div className="sec-head">
        <h2>Classes, weakest first</h2>
        <span className="spacer" />
        <span className="sub">{list.data?.length ?? 0} sections</span>
      </div>
      <p className="sec-note">
        Open any class for its description, teacher and schedule, and how it is going: results over
        time, work handed in, attendance, and which students need support. The weakest strand column
        names the part of the course a low average comes from.
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
                    <button className="rowbtn" onClick={() => onOpenClass(c.code)}>{c.title}</button>
                    <div className="sub">
                      <span className="code">{c.code}</span> · {c.dept} · {c.length === 'semester' ? 'Semester' : 'Year'} ·{' '}
                      {c.enrolled}/{c.capacity} seats{c.waitlist > 0 && <> · {c.waitlist} waiting</>}
                    </div>
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
                      <>{c.weakest_skill} {c.weakest_skill_mean !== null && <b>{pctText(c.weakest_skill_mean)}</b>}</>
                    ) : <span className="sub">—</span>}
                  </td>
                  <td className="nowrap"><button className="btn sm" onClick={() => onOpenClass(c.code)}>View class</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

const pct = (x: number | null | undefined, digits = 0) =>
  x === null || x === undefined ? '—' : `${(x * 100).toFixed(digits)}%`

function ClassPage({ code, onBack, onOpenClass, onOpenStudent }: {
  code: string
  onBack: () => void
  onOpenClass: (code: string) => void
  onOpenStudent: (sid: string) => void
}) {
  const detail = useApi(() => api.course(code), [code])

  return (
    <>
      <div style={{ marginBottom: 12 }}>
        <button className="btn sm ghost" onClick={onBack}>← All classes</button>
      </div>
      {detail.loading && <Loading what={code} />}
      {detail.error && <ErrorNote error={detail.error} onRetry={detail.reload} />}
      {detail.data && <ClassBody d={detail.data} onOpenClass={onOpenClass} onOpenStudent={onOpenStudent} />}
    </>
  )
}

function ClassBody({ d, onOpenClass, onOpenStudent }: {
  d: CourseDetail
  onOpenClass: (code: string) => void
  onOpenStudent: (sid: string) => void
}) {
  const { me } = useAuth()
  const c = d.course
  const s = d.stats
  const activePlans = d.plans.filter((p) => p.status === 'active')

  return (
    <>
      <section className="sec">
        <div className="sec-head" style={{ alignItems: 'baseline' }}>
          <h2 style={{ fontSize: 24 }}>{c.title}</h2>
          <span className="sub">
            <span className="code">{c.code}</span> · {c.dept} · {c.length === 'semester' ? 'One semester' : 'Full year'} · {c.credits} credit{c.credits === 1 ? '' : 's'}
          </span>
          <span className="spacer" />
          {c.class_mean !== null && <Pill kind={gradeStatus(c.class_mean)}>class average {pctText(c.class_mean)}</Pill>}
        </div>

        <div className="split">
          <div className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="eyebrow">About this class</div>
            <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55 }}>
              {c.description || 'No description is recorded for this class.'}
            </p>
            <dl className="kv" style={{ margin: 0 }}>
              <dt>Prerequisite</dt><dd>{c.prerequisite || 'None'}</dd>
              <dt>UC approved</dt><dd>{c.uc_approved ? 'Yes' : 'Not listed as UC approved'}</dd>
              {c.extra_period && <><dt>Scheduling</dt><dd>Extra Period Option — outside the 5–6 class load</dd></>}
              {!c.graded && <><dt>Grading</dt><dd>Ungraded in the course of study; this app still records scores</dd></>}
            </dl>
            {c.catalog_page !== null && (
              <div className="sub">
                Course of study 2026–27, p. {c.catalog_page}
                {c.legacy_title && c.legacy_title !== c.title && <> · formerly listed here as {c.legacy_title}</>}
              </div>
            )}
          </div>

          <div className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="eyebrow">Teacher and schedule</div>
            <div style={{ fontSize: 17, fontWeight: 600 }}>{c.teacher}</div>
            <dl className="kv" style={{ margin: 0 }}>
              <dt>When</dt><dd>{c.period > 0 ? `Period ${c.period}` : 'Outside the timetable'}</dd>
              <dt>Room</dt><dd>{c.room}</dd>
              <dt>Seats</dt><dd>{c.enrolled} of {c.capacity} filled{c.waitlist > 0 && <> · {c.waitlist} on the waitlist</>}</dd>
            </dl>
            {d.teacher && d.teacher.sections.length > 1 && (
              <>
                <div className="sub">
                  {c.teacher} teaches {d.teacher.sections.length} sections, {d.teacher.students_taught} students in all:
                </div>
                <div className="people">
                  {d.teacher.sections.map((t) => (
                    <div className="person" key={t.code}>
                      <span className="pn">
                        {t.code === c.code ? <b>{t.title}</b> : (
                          <button className="rowbtn" onClick={() => onOpenClass(t.code)}>{t.title}</button>
                        )}
                        <div className="sub"><span className="code">{t.code}</span> · P{t.period} · {t.room} · {t.enrolled} students</div>
                      </span>
                      {t.class_mean !== null && <span className="nowrap sub">{pctText(t.class_mean)}</span>}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </section>

      <section className="sec">
        <div className="sec-head"><h2>How the class is doing</h2></div>
        {s && (
          <div className="strip" style={{ marginBottom: 16 }}>
            <Stat k="Class average" v={c.class_mean === null ? '—' : pctText(c.class_mean)}
              c={s.median !== null ? `median ${pctText(s.median)} · ${s.students} students` : `${s.students} students`} />
            <Stat k="Work handed in" v={pct(s.completion_rate)}
              c={s.late_rate !== null ? `${pct(s.late_rate)} of it late` : undefined} />
            <Stat k="Trend" v={s.mean_trend === null ? '—' : `${s.mean_trend > 0 ? '+' : ''}${s.mean_trend} pts`}
              c={`${s.improving} improving · ${s.declining} slipping`} />
            <Stat k="Attendance" v={s.absence_rate === null ? '—' : pct(1 - s.absence_rate)}
              c="average across this class's students" />
            <Stat k="Need support" v={s.needs_plan + s.watch}
              c={`${s.needs_plan} need a plan · ${s.watch} to watch · ${c.excelling} excelling`} />
          </div>
        )}

        <div className="chartcard" style={{ marginBottom: 16 }}>
          <div className="chart-title">Results over time</div>
          <div className="chart-sub">Class average on each graded piece of work, in the order it was due. The dashed line is the 72% support line.</div>
          <div className="chart-scroll"><AssessmentTrend rows={d.assessments} code={c.code} /></div>
        </div>

        <div className="split">
          <div className="chartcard">
            <div className="chart-title">Strand averages</div>
            <div className="chart-sub">Where this cohort is strong and where the course itself needs another pass.</div>
            <div className="chart-scroll">
              <RankedBars
                ariaLabel={`Strand averages for ${c.code}`}
                labelWidth={180}
                rows={d.skills.map((g) => ({
                  key: g.skill, label: g.skill, value: g.class_mean, status: gradeStatus(g.class_mean),
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
            <div className="chart-sub">How the {d.students.length} students in this class sit.</div>
            <div className="chart-scroll">
              <Columns
                ariaLabel={`Grade distribution for ${c.code}`}
                rows={d.distribution}
                highlight={(label) => (label === 'Below 60' ? 'critical' : label === '60–69' ? 'serious' : label === '70–79' ? 'warning' : 'accent')}
              />
            </div>
          </div>
        </div>
      </section>

      <ClassPlans code={c.code} />

      <section className="sec">
        <div className="sec-head">
          <h2>Assignments and tests</h2>
          <span className="spacer" />
          <span className="sub">{d.assessments.length} graded so far</span>
        </div>
        <div className="tblwrap">
          <table className="tbl">
            <caption className="visually-hidden">Graded work in {c.code}, in the order it was due</caption>
            <thead>
              <tr>
                <th scope="col">Due</th>
                <th scope="col">Work</th>
                <th scope="col">Class average</th>
                <th scope="col" className="num">Handed in</th>
                <th scope="col" className="num">Late</th>
              </tr>
            </thead>
            <tbody>
              {d.assessments.length === 0 && <tr><td colSpan={5} className="empty">Nothing graded yet.</td></tr>}
              {d.assessments.map((a) => (
                <tr key={a.id}>
                  <td className="nowrap sub">{a.due_on}</td>
                  <td>{a.title}<div className="sub">{a.kind} · {a.skill}</div></td>
                  <td style={{ minWidth: 130 }}>
                    {a.class_mean === null ? <span className="sub">no work in</span> : (
                      <Meter value={a.class_mean} kind={gradeStatus(a.class_mean)} label={pctText(a.class_mean)} />
                    )}
                  </td>
                  <td className="num">
                    {a.submitted}/{a.submitted + a.missing}
                    {a.missing > 0 && <div className="sub">{a.missing} missing</div>}
                  </td>
                  <td className="num">{a.late || <span className="sub">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="sec">
        <div className="sec-head">
          <h2>Students</h2>
          <span className="spacer" />
          <span className="sub">lowest grade first · open a student for their full record</span>
        </div>
        <div className="tblwrap">
          <table className="tbl">
            <caption className="visually-hidden">Students in {c.code}, lowest grade first</caption>
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
              {d.students.map((r) => (
                <tr key={r.sid}>
                  <td>
                    <button className="rowbtn" onClick={() => onOpenStudent(r.sid)}>{r.name}</button>
                    <div className="sub"><span className="code">{r.sid}</span> · Gr {r.grade}</div>
                  </td>
                  <td style={{ minWidth: 130 }}><Meter value={r.pct} kind={gradeStatus(r.pct)} label={pctText(r.pct)} /></td>
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
      </section>

      <section className="sec">
        <div className="split">
          <div>
            <div className="sec-head">
              <h2>Support plans in this class</h2>
              <span className="spacer" />
              <span className="sub">{activePlans.length} open</span>
            </div>
            <div className="panelbox panelbox-pad">
              {d.plans.length === 0 ? <p className="sub" style={{ margin: 0 }}>No support plans are tied to this class.</p> : (
                <div className="people">
                  {d.plans.map((p) => (
                    <div className="person" key={p.id}>
                      <span className="pn">
                        <button className="rowbtn" onClick={() => onOpenStudent(p.sid)}>{p.student_name}</button>
                        <div className="sub">{p.title} · {p.kind} · {p.owner}</div>
                      </span>
                      <Pill kind={p.status === 'active' ? 'accent' : 'neutral'}>{p.status}</Pill>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          {me.modules.includes('stockroom') && <div>
            <div className="sec-head"><h2>Supplies this class uses</h2></div>
            <div className="panelbox panelbox-pad">
              {d.supplies.length === 0 ? <p className="sub" style={{ margin: 0 }}>No stockroom items are linked to this class.</p> : (
                <div className="people">
                  {d.supplies.map((i) => (
                    <div className="person" key={i.sku}>
                      <span className="pn">
                        {i.name}
                        <div className="sub"><span className="code">{i.sku}</span> · {i.on_hand} of {i.par} on hand{i.requisitioned && ' · on order'}</div>
                      </span>
                      <Pill kind={i.status}>{i.status_label}</Pill>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>}
        </div>
      </section>
    </>
  )
}

const STATUS_FILL: Record<string, string> = {
  critical: 'var(--critical)', serious: 'var(--serious)', warning: 'var(--warning)',
  accent: 'var(--accent)', good: 'var(--good)', neutral: 'var(--ink-3)',
}

/** One bar per graded piece of work, with the 72% support line drawn across. */
function AssessmentTrend({ rows, code }: { rows: CourseAssessmentRow[]; code: string }) {
  const { show, hide, node } = useTooltip()
  const graded = rows.filter((r) => r.class_mean !== null)
  if (graded.length === 0) return <p className="sub" style={{ margin: 0 }}>Nothing graded yet.</p>
  // Wide enough to fill a desktop card; below 560px the card's own scroller takes over.
  const W = Math.max(1000, graded.length * 60 + 60), H = 210, padL = 34, padR = 12, padT = 14, padB = 34
  const band = (W - padL - padR) / graded.length
  const barW = Math.min(34, band - 14)
  const y = (v: number) => padT + (1 - v / 100) * (H - padT - padB)
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ minWidth: 560, display: 'block' }}
        role="img" aria-label={`Class average on each graded piece of work in ${code}`}>
        {[0, 50, 100].map((t) => (
          <g key={t}>
            <line className="gridline" x1={padL} y1={y(t)} x2={W - padR} y2={y(t)} />
            <text x={padL - 8} y={y(t)} fontSize="10" textAnchor="end" dominantBaseline="middle">{t}</text>
          </g>
        ))}
        <line x1={padL} x2={W - padR} y1={y(72)} y2={y(72)} stroke="var(--serious)" strokeDasharray="4 3" strokeWidth={1} />
        {graded.map((r, i) => {
          const v = r.class_mean as number
          const cx = padL + band * i + band / 2
          return (
            <g key={r.id}
              onMouseMove={(e) => show(e, <TipRows title={r.title} rows={[
                ['Due', r.due_on], ['Class average', pctText(v)],
                ['Handed in', `${r.submitted} of ${r.submitted + r.missing}`], ['Late', String(r.late)],
              ]} />)}
              onMouseLeave={hide}>
              <rect x={cx - barW / 2} y={y(v)} width={barW} height={Math.max(0, y(0) - y(v))} rx={2}
                fill={STATUS_FILL[gradeStatus(v)]} />
              <text x={cx} y={H - padB + 14} fontSize="9.5" textAnchor="middle">{r.due_on.slice(5)}</text>
              <text x={cx} y={H - padB + 25} fontSize="9" textAnchor="middle" opacity={0.7}>{r.kind}</text>
            </g>
          )
        })}
      </svg>
      {node}
    </>
  )
}
