import { useState } from 'react'
import { api } from '../api'
import { useApi } from '../useApi'
import { ErrorNote, Loading, Pill } from '../components/ui'

export function Plans({ onOpenStudent, onChanged }: {
  onOpenStudent: (sid: string) => void
  onChanged?: () => void
}) {
  const [status, setStatus] = useState('active')
  const { data, error, loading, reload } = useApi(() => api.interventions(status || undefined), [status])

  async function set(id: number, next: 'completed' | 'declined' | 'active') {
    await api.updateIntervention(id, { status: next })
    reload()
    onChanged?.()   // the open-plans count in the tab badge moved
  }
  async function remove(id: number) {
    await api.deleteIntervention(id)
    reload()
    onChanged?.()
  }

  return (
    <section className="sec">
      <div className="sec-head">
        <h2>Support plans</h2>
        <span className="spacer" />
        <span className="sub">{data?.length ?? 0} plans</span>
      </div>
      <p className="sec-note">
        Recommendations are computed; plans are chosen. Each one records who owns it and the reasoning
        it was opened on, so a review in three weeks can tell whether it worked.
      </p>

      <div className="filters">
        <div className="field">
          <label htmlFor="pl-status">Status</label>
          <select id="pl-status" className="inp" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="active">Active</option>
            <option value="completed">Completed</option>
            <option value="declined">Declined</option>
            <option value="">All</option>
          </select>
        </div>
      </div>

      {loading && <Loading what="plans" />}
      {error && <ErrorNote error={error} onRetry={reload} />}
      {data && data.length === 0 && (
        <div className="panelbox"><div className="qempty">No plan has this status.</div></div>
      )}
      {data && data.length > 0 && (
        <div className="tblwrap">
          <table className="tbl">
            <caption className="visually-hidden">Support plans with their owner and status</caption>
            <thead>
              <tr>
                <th scope="col">Plan</th>
                <th scope="col">Student</th>
                <th scope="col">Kind</th>
                <th scope="col">Owner</th>
                <th scope="col">Opened</th>
                <th scope="col">Status</th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {data.map((iv) => (
                <tr key={iv.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{iv.title}</div>
                    {iv.rationale && <div className="sub" style={{ maxWidth: 380 }}>{iv.rationale}</div>}
                  </td>
                  <td className="nowrap">
                    <button className="rowbtn" onClick={() => onOpenStudent(iv.student_sid)}>{iv.student_name}</button>
                    <div className="sub"><span className="code">{iv.student_sid}</span></div>
                  </td>
                  <td className="nowrap sub">
                    {iv.kind}
                    {iv.course_code && <div><span className="code">{iv.course_code}</span></div>}
                  </td>
                  <td className="nowrap sub">{iv.owner}</td>
                  <td className="nowrap sub">{iv.opened_on}</td>
                  <td>
                    <Pill kind={iv.status === 'active' ? 'accent' : iv.status === 'completed' ? 'good' : 'neutral'}>
                      {iv.status}
                    </Pill>
                  </td>
                  <td className="nowrap">
                    {iv.status === 'active' ? (
                      <>
                        <button className="btn sm" onClick={() => set(iv.id, 'completed')}>Done</button>{' '}
                        <button className="btn sm ghost" onClick={() => set(iv.id, 'declined')}>Declined</button>
                      </>
                    ) : (
                      <>
                        <button className="btn sm ghost" onClick={() => set(iv.id, 'active')}>Reopen</button>{' '}
                        <button className="btn sm ghost" onClick={() => remove(iv.id)}>Delete</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
