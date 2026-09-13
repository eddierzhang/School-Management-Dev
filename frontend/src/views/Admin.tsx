import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import { useApi } from '../useApi'
import type { AdminUser, AuditEvent, ImportReport, Role } from '../types'
import { ErrorNote, Loading, Pill } from '../components/ui'

const ROLE_OPTIONS: { role: Role; label: string }[] = [
  { role: 'counselor', label: 'Counselor / support staff' },
  { role: 'teacher', label: 'Teacher' },
  { role: 'registrar', label: 'Registrar' },
  { role: 'business', label: 'Business office' },
  { role: 'admin', label: 'Administrator' },
]

const when = (iso: string | null) => (iso ? new Date(iso + 'Z').toLocaleString() : '—')

export function Admin() {
  const { can } = useAuth()
  const [section, setSection] = useState<'users' | 'audit' | 'import'>(can('users.manage') ? 'users' : 'audit')
  return (
    <>
      <div className="groupbar" role="tablist" aria-label="Administration">
        {can('users.manage') && (
          <button className="groupbtn" aria-pressed={section === 'users'} onClick={() => setSection('users')}>Accounts</button>
        )}
        {can('audit.read') && (
          <button className="groupbtn" aria-pressed={section === 'audit'} onClick={() => setSection('audit')}>Audit log</button>
        )}
        {can('data.import') && (
          <button className="groupbtn" aria-pressed={section === 'import'} onClick={() => setSection('import')}>Import records</button>
        )}
      </div>
      {section === 'users' && <Users />}
      {section === 'audit' && <Audit />}
      {section === 'import' && <Import />}
    </>
  )
}

function Import() {
  const [file, setFile] = useState<File | null>(null)
  const [teachers, setTeachers] = useState(false)
  const [report, setReport] = useState<ImportReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(apply: boolean) {
    if (!file) return
    setBusy(true); setError(null)
    try {
      setReport(await api.importOneRoster(file, apply, teachers))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The file could not be checked.')
    } finally { setBusy(false) }
  }

  const counts = (c: Record<string, number>) =>
    Object.entries(c).map(([k, v]) => `${v} ${k}`).join(', ') || 'nothing'

  return (
    <section className="sec">
      <div className="sec-head"><h2>Import records</h2></div>
      <p className="sec-note">
        Upload a OneRoster 1.1 CSV export from the student information system, as a zip: users, classes and
        enrollments, plus lineItems, results and attendance if you have them. Checking a file changes nothing.
        It shows exactly what the import would create, update and drop, and any error refuses the whole import.
        A student missing from a class’s roster is marked dropped, never deleted.
      </p>
      <div className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 14 }}>
        <div className="filters" style={{ marginBottom: 0 }}>
          <div className="field grow">
            <label htmlFor="imp-file">OneRoster zip</label>
            <input id="imp-file" className="inp" type="file" accept=".zip"
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); setReport(null) }} />
          </div>
          <label className="toggle">
            <input type="checkbox" checked={teachers} onChange={(e) => setTeachers(e.target.checked)} />
            Create teacher accounts for school sign-in
          </label>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" disabled={!file || busy} onClick={() => void run(false)}>
            {busy ? 'Working…' : 'Check the file'}
          </button>
          {report && report.ok && !report.applied && (
            <button className="btn primary" disabled={busy} onClick={() => void run(true)}>Import these records</button>
          )}
        </div>
      </div>
      {error && <ErrorNote error={error} />}
      {report && (
        <div className="panelbox panelbox-pad" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {report.applied ? <Pill kind="good">Imported</Pill>
              : report.ok ? <Pill kind="accent">Ready to import</Pill>
              : <Pill kind="critical">{report.errors.length} error{report.errors.length === 1 ? '' : 's'} — nothing imported</Pill>}
            <span className="sub">Rows read: {counts(report.rows)}</span>
          </div>
          {report.ok && (
            <dl className="kv" style={{ maxWidth: 560 }}>
              <dt>{report.applied ? 'Created' : 'Would create'}</dt><dd>{counts(report.created)}</dd>
              <dt>{report.applied ? 'Updated' : 'Would update'}</dt><dd>{counts(report.updated)}</dd>
              <dt>{report.applied ? 'Dropped' : 'Would drop'}</dt><dd>{report.dropped_enrollments} enrollments</dd>
            </dl>
          )}
          {[['Errors', report.errors, 'critical'] as const, ['Warnings', report.warnings, 'warning'] as const]
            .filter(([, list]) => list.length > 0).map(([label, list, kind]) => (
              <div key={label}>
                <div className="eyebrow" style={{ marginBottom: 6 }}>{label}</div>
                <div className="tblwrap">
                  <table className="tbl" style={{ minWidth: 0 }}>
                    <tbody>
                      {list.map((i, n) => (
                        <tr key={n}>
                          <td className="nowrap"><Pill kind={kind}>{i.file}{i.line ? `:${i.line}` : ''}</Pill></td>
                          <td>{i.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
        </div>
      )}
    </section>
  )
}

function Users() {
  const users = useApi(() => api.users(), [])
  const { me } = useAuth()
  const [error, setError] = useState<string | null>(null)

  async function change(u: AdminUser, body: Parameters<typeof api.updateUser>[1]) {
    setError(null)
    try { await api.updateUser(u.id, body); users.reload() } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That change did not save.')
    }
  }

  return (
    <section className="sec">
      <div className="sec-head"><h2>Accounts</h2></div>
      <p className="sec-note">
        People sign in with the school account whose email matches, or with a password if one is set.
        Changing someone’s role or deactivating them ends their sessions at once. A teacher only sees
        the students in sections taught under their teacher name.
      </p>
      <NewUserForm onCreated={users.reload} />
      {error && <ErrorNote error={error} />}
      {users.loading && <Loading what="accounts" />}
      {users.error && <ErrorNote error={users.error} onRetry={users.reload} />}
      {users.data && (
        <div className="tblwrap">
          <table className="tbl">
            <thead>
              <tr><th>Name</th><th>Role</th><th>Teacher name</th><th>Sign-in</th><th>Last signed in</th><th /></tr>
            </thead>
            <tbody>
              {users.data.map((u) => (
                <tr key={u.id} style={u.active ? undefined : { opacity: 0.6 }}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{u.name}</div>
                    <div className="sub">{u.email}</div>
                  </td>
                  <td>
                    <select className="inp" value={u.role} aria-label={`Role for ${u.name}`}
                      disabled={u.id === me.id}
                      onChange={(e) => {
                        const role = e.target.value as Role
                        const teacher_name = role === 'teacher' ? window.prompt('Teacher name, exactly as on the timetable') : null
                        if (role === 'teacher' && !teacher_name) return
                        void change(u, { role, teacher_name })
                      }}>
                      {ROLE_OPTIONS.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
                    </select>
                  </td>
                  <td>{u.teacher_name ?? <span className="sub">—</span>}</td>
                  <td><span className="sub">{u.has_password ? 'School account or password' : 'School account only'}</span></td>
                  <td className="nowrap"><span className="sub">{when(u.last_login_at)}</span></td>
                  <td className="nowrap">
                    {u.active
                      ? u.id !== me.id && <button className="btn sm ghost" onClick={() => change(u, { active: false })}>Deactivate</button>
                      : <><Pill kind="neutral">inactive</Pill> <button className="btn sm" onClick={() => change(u, { active: true })}>Reactivate</button></>}
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

function NewUserForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ email: '', name: '', role: 'counselor' as Role, teacher_name: '', password: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await api.createUser({ email: form.email, name: form.name, role: form.role,
        teacher_name: form.role === 'teacher' ? form.teacher_name : null, password: form.password || null })
      setForm({ email: '', name: '', role: 'counselor', teacher_name: '', password: '' })
      setOpen(false)
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'The account was not created.')
    } finally { setBusy(false) }
  }

  if (!open) return <button className="btn primary" style={{ marginBottom: 14 }} onClick={() => setOpen(true)}>Add an account</button>
  return (
    <form className="panelbox panelbox-pad" style={{ marginBottom: 14, display: 'flex', flexDirection: 'column', gap: 10 }} onSubmit={submit}>
      {error && <ErrorNote error={error} />}
      <div className="filters" style={{ marginBottom: 0 }}>
        <div className="field grow"><label htmlFor="nu-name">Name</label><input id="nu-name" className="inp" required value={form.name} onChange={set('name')} /></div>
        <div className="field grow"><label htmlFor="nu-email">Email</label><input id="nu-email" className="inp" type="email" required value={form.email} onChange={set('email')} /></div>
        <div className="field">
          <label htmlFor="nu-role">Role</label>
          <select id="nu-role" className="inp" value={form.role} onChange={set('role')}>
            {ROLE_OPTIONS.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
          </select>
        </div>
        {form.role === 'teacher' && (
          <div className="field grow"><label htmlFor="nu-teacher">Teacher name on the timetable</label>
            <input id="nu-teacher" className="inp" required value={form.teacher_name} onChange={set('teacher_name')} placeholder="e.g. R. Okonkwo" /></div>
        )}
        <div className="field grow"><label htmlFor="nu-pass">Password (optional)</label>
          <input id="nu-pass" className="inp" type="password" autoComplete="new-password" minLength={12} value={form.password} onChange={set('password')} placeholder="Leave empty for school sign-in only" /></div>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn primary" type="submit" disabled={busy}>Create account</button>
        <button className="btn ghost" type="button" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </form>
  )
}

function Audit() {
  const [filters, setFilters] = useState({ actor: '', action: '', entity_id: '' })
  const [applied, setApplied] = useState(filters)
  const [more, setMore] = useState<AuditEvent[]>([])
  const [next, setNext] = useState<number | null>(null)
  const page = useApi(async () => {
    const p = await api.audit(clean(applied))
    setMore([]); setNext(p.next_before_id)
    return p
  }, [applied])

  async function loadMore() {
    if (next === null) return
    const p = await api.audit({ ...clean(applied), before_id: next })
    setMore((m) => [...m, ...p.events]); setNext(p.next_before_id)
  }

  const rows = [...(page.data?.events ?? []), ...more]
  return (
    <section className="sec">
      <div className="sec-head"><h2>Audit log</h2></div>
      <p className="sec-note">
        Every change made through the system, including refused attempts; every time someone opened
        a student’s record, documents or plans; and every sign-in. Newest first. Entries cannot be edited.
      </p>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setApplied(filters) }}>
        <div className="field grow"><label htmlFor="au-actor">Person (email)</label>
          <input id="au-actor" className="inp" value={filters.actor} onChange={(e) => setFilters({ ...filters, actor: e.target.value })} /></div>
        <div className="field grow"><label htmlFor="au-action">Action starts with</label>
          <input id="au-action" className="inp" value={filters.action} placeholder="student.view, POST, auth." onChange={(e) => setFilters({ ...filters, action: e.target.value })} /></div>
        <div className="field"><label htmlFor="au-entity">Record</label>
          <input id="au-entity" className="inp" value={filters.entity_id} placeholder="S-1507" onChange={(e) => setFilters({ ...filters, entity_id: e.target.value })} /></div>
        <button className="btn" type="submit">Filter</button>
      </form>
      {page.loading && <Loading what="the audit log" />}
      {page.error && <ErrorNote error={page.error} onRetry={page.reload} />}
      {page.data && (
        <div className="tblwrap">
          <table className="tbl">
            <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Record</th><th className="num">Result</th><th>From</th></tr></thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={6} className="sub">Nothing matches.</td></tr>}
              {rows.map((e) => (
                <tr key={e.id}>
                  <td className="nowrap"><span className="sub">{when(e.at)}</span></td>
                  <td>{e.actor_email || <span className="sub">—</span>}{e.actor_role && <div className="sub">{e.actor_role}</div>}</td>
                  <td><span className="code">{e.action}</span></td>
                  <td>{e.entity_type ? <><span className="sub">{e.entity_type}</span> <span className="code">{e.entity_id}</span></> : <span className="sub">—</span>}</td>
                  <td className="num">{e.status !== null && <Pill kind={e.status < 300 ? 'good' : e.status < 500 ? 'warning' : 'critical'}>{e.status}</Pill>}</td>
                  <td><span className="sub code">{e.ip}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {next !== null && <button className="btn" style={{ marginTop: 12 }} onClick={loadMore}>Older entries</button>}
    </section>
  )
}

function clean(f: Record<string, string>) {
  return Object.fromEntries(Object.entries(f).filter(([, v]) => v.trim()).map(([k, v]) => [k, v.trim()]))
}
