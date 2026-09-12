import { api } from '../api'
import { useApi } from '../useApi'
import {
  FleetCards, FleetMessages, ProposalInbox, RunDrawer, RunHistory, RuntimeNotice, useFleet,
} from '../components/fleet'
import { RankedBars, TipRows } from '../components/charts'
import { BandPill, ErrorNote, Icon, Loading, Stat, gradeStatus, pctText } from '../components/ui'

export function Overview({ onOpenStudent, onGoto, onChanged }: {
  onOpenStudent: (sid: string) => void
  onGoto: (tab: string) => void
  onChanged?: () => void
}) {
  const summary = useApi(() => api.summary(), [])
  const queue = useApi(() => api.watchlist(8, true), [])
  const active = useApi(() => api.interventions('active'), [])
  // Approving here must also refresh this page's own figures, not just the
  // tab badges — the plan it opens is one of the numbers on screen.
  const f = useFleet(() => {
    summary.reload()
    active.reload()
    queue.reload()
    onChanged?.()
  })

  if (summary.loading || queue.loading) return <Loading what="the term" />
  if (summary.error) return <ErrorNote error={summary.error} onRetry={summary.reload} />
  if (!summary.data) return null
  const s = summary.data

  return (
    <>
      <section className="sec">
        <div className="strip">
          <Stat k="Needs a plan" v={s.needs_plan} c={`of ${s.students} students`} />
          <Stat k="Watching" v={s.watch} c="one factor short of a plan" />
          <Stat k="Excelling" v={s.excelling} c="something to build on" />
          <Stat k="Plans open" v={s.open_interventions} c={s.unaddressed > 0 ? `${s.unaddressed} flagged students have none` : 'every flagged student has one'} />
        </div>
      </section>

      {s.unaddressed > 0 && (
        <div className="banner critical">
          <Icon name="critical" />
          <span style={{ flex: 1, minWidth: 220 }}>
            <b>{s.unaddressed} students need a plan and do not have one.</b> They are ranked below,
            worst first.
          </span>
          <button className="btn sm" onClick={() => onGoto('watchlist')}>Open struggling students</button>
        </div>
      )}

      {f.proposals.length > 0 && (
        <section className="sec">
          <div className="sec-head">
            <h2>Agents are waiting on you</h2>
            <span className="spacer" />
            <span className="sub">{f.proposals.length} pending</span>
          </div>
          <p className="sec-note">
            Nothing here has happened yet. Approving runs deterministic code that re-checks the
            proposal against current records.
          </p>
          <ProposalInbox f={f} emptyNote={false} />
        </section>
      )}

      <section className="sec">
        <div className="sec-head">
          <h2>Agent fleet</h2>
          <span className="spacer" />
          <button className="btn sm" onClick={() => onGoto('agents')}>
            Transcripts and custom tasks
          </button>
        </div>
        <p className="sec-note">
          Each agent reads its own corner of the school and proposes changes for you to approve —
          it can never make one itself. Give one a task in its own words, or leave the box blank to
          run the sweep described in it. Runs take a couple of minutes on the local model.
        </p>
        <RuntimeNotice f={f} />
        <FleetMessages f={f} />
        <FleetCards f={f} />
        {f.runs.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Latest runs</div>
            <RunHistory f={f} limit={3} />
          </div>
        )}
      </section>

      <section className="sec">
        <div className="split">
          <div>
            <div className="sec-head">
              <h2>Act on this first</h2>
            </div>
            <p className="sec-note">
              Ranked by the struggle index, which weights how far below the line a grade is, whether
              it is falling, how much work is unsubmitted, and attendance. Each student carries the
              reasons that put them here.
            </p>
            <div className="panelbox queue">
              {queue.data?.length === 0 && <div className="qempty">Nobody is currently flagged.</div>}
              {queue.data?.map((st) => {
                const rec = st.recommendations[0]
                const reason = st.reasons.find((r) => r.kind === 'concern')
                return (
                  <div className="qrow" key={st.sid} style={{ ['--sev' as string]: st.band === 'needs-plan' ? 'var(--critical)' : 'var(--serious)' }}>
                    <div className="qbody">
                      <div className="qtitle">
                        <button className="rowbtn" onClick={() => onOpenStudent(st.sid)}>{st.name}</button>{' '}
                        <span className="sub">Gr {st.grade} · {st.homeroom}</span>
                      </div>
                      <div className="qmeta">{reason ? `${reason.label}. ${reason.detail}` : 'Flagged by the index.'}</div>
                      {rec && <div className="qmeta" style={{ marginTop: 3 }}><b>Do:</b> {rec.title}</div>}
                    </div>
                    <BandPill band={st.band} />
                    <button className="btn sm" onClick={() => onOpenStudent(st.sid)}>Open</button>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="panelbox panelbox-pad">
            <div className="eyebrow" style={{ marginBottom: 9 }}>Term at a glance</div>
            <dl className="kv">
              <dt>Term</dt><dd>{s.term}</dd>
              <dt>As of</dt><dd>{s.today}</dd>
              <dt>Classes</dt><dd>{s.courses}</dd>
              <dt>Graded so far</dt><dd>{s.graded_assessments} pieces</dd>
              <dt>Attendance</dt><dd>{pctText(s.mean_attendance * 100)}</dd>
            </dl>
            <p className="sub" style={{ marginTop: 12 }}>
              Every index is recomputed from the gradebook when you load a page. Record a grade and
              the ranking moves — there is no cached risk score to refresh.
            </p>

            <div className="eyebrow" style={{ margin: '18px 0 9px' }}>Already in flight</div>
            {active.data && active.data.length === 0 && (
              <p className="sub" style={{ margin: 0 }}>No support plan is open yet.</p>
            )}
            {active.data?.slice(0, 6).map((iv) => (
              <div key={iv.id} style={{ paddingBlock: 7, borderTop: '1px solid var(--rule)' }}>
                <div style={{ fontSize: 12.5, fontWeight: 600 }}>{iv.title}</div>
                <div className="sub">
                  <button className="rowbtn" style={{ fontSize: 11.5 }} onClick={() => onOpenStudent(iv.student_sid)}>
                    {iv.student_name}
                  </button>
                  {' · '}{iv.owner}
                  {iv.course_code && <> · <span className="code">{iv.course_code}</span></>}
                </div>
              </div>
            ))}
            {active.data && active.data.length > 6 && (
              <button className="btn sm ghost" style={{ marginTop: 8 }} onClick={() => onGoto('plans')}>
                See all {active.data.length} plans
              </button>
            )}
          </div>
        </div>
      </section>

      <section className="sec">
        <div className="sec-head">
          <h2>Strands the whole class is missing</h2>
          <span className="spacer" />
          <button className="btn sm" onClick={() => onGoto('skills')}>See every strand</button>
        </div>
        <p className="sec-note">
          One student below on a strand is a tutoring referral. Half the class below on it is a lesson
          to run again — and no amount of tutoring fixes that one student at a time.
        </p>
        <div className="chartcard">
          <div className="chart-title">Weakest strands, class average</div>
          <div className="chart-sub">Across every class. The number is the cohort mean for that strand.</div>
          <div className="chart-scroll">
            <RankedBars
              ariaLabel="Weakest skill strands school-wide"
              labelWidth={240}
              rows={s.top_skill_gaps.map((g) => ({
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
          <table className="tbl visually-hidden">
            <caption>Weakest strands, class average</caption>
            <thead><tr><th>Strand</th><th>Class</th><th>Class average</th><th>Students below</th></tr></thead>
            <tbody>
              {s.top_skill_gaps.map((g) => (
                <tr key={g.course_code + g.skill}>
                  <td>{g.skill}</td><td>{g.course_code}</td><td>{pctText(g.class_mean)}</td>
                  <td>{g.students_below} of {g.cohort}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <RunDrawer f={f} />
    </>
  )
}
