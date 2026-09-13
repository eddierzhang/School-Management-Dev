import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api'
import { useApi } from '../useApi'
import type { AuthConfig, Role } from '../types'

const ERRORS: Record<string, string> = {
  'not-registered': 'Your school account signed in, but it has no access here. Ask an administrator to add you, or request an account below.',
  'sign-in-failed': 'Signing in with your school account did not complete. Try again.',
  'provider-unavailable': 'The school sign-in service could not be reached. Try again shortly.',
}

export function Login({ onSignedIn }: { onSignedIn: () => void }) {
  const config = useApi(() => api.authConfig(), [])
  const [mode, setMode] = useState<'sign-in' | 'request'>('sign-in')
  const c = config.data

  return (
    <div className="login-wrap">
      <main className="login-card" aria-labelledby="login-title">
        <div className="eyebrow">{c?.school ?? 'Student Support Platform'}</div>
        {mode === 'sign-in' || !c?.signup
          ? <SignIn config={c} onSignedIn={onSignedIn} onRequest={() => setMode('request')} />
          : <RequestAccount config={c} onBack={() => setMode('sign-in')} />}
      </main>
    </div>
  )
}

function SignIn({ config: c, onSignedIn, onRequest }: {
  config: AuthConfig | null; onSignedIn: () => void; onRequest: () => void
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const code = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('error')
  const [error, setError] = useState<string | null>(code ? ERRORS[code] ?? 'Sign-in failed.' : null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await api.login(email, password)
      if (window.location.hash.startsWith('#/login')) window.history.replaceState(null, '', '#/overview')
      onSignedIn()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h1 id="login-title">Student support office</h1>
      <p className="sub" style={{ margin: 0 }}>
        Student records are confidential. Everything you view and change here is recorded.
      </p>

      {error && <div className="banner critical" role="alert" style={{ margin: 0 }}>{error}</div>}

      {c?.oidc && (
        <a className="btn primary login-sso" href="/api/auth/oidc/login">{c.oidc_label}</a>
      )}

      {c?.password_login && (
        <form onSubmit={submit} className="login-form">
          {c.oidc && <div className="login-or"><span>or with a password</span></div>}
          <div className="field">
            <label htmlFor="login-email">Email</label>
            <input id="login-email" className="inp" type="email" autoComplete="username" required
              value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="login-password">Password</label>
            <input id="login-password" className="inp" type="password" autoComplete="current-password" required
              value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button className={`btn ${c.oidc ? '' : 'primary'}`} type="submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      )}

      {c?.signup && (
        <p className="sub login-switch">
          New here? <button type="button" className="linkbtn" onClick={onRequest}>Create an account</button>
        </p>
      )}
    </>
  )
}

function RequestAccount({ config: c, onBack }: { config: AuthConfig; onBack: () => void }) {
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '',
    requested_role: (c.signup_roles[0]?.role ?? 'teacher') as Role, note: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const mismatch = form.confirm.length > 0 && form.confirm !== form.password

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (form.password !== form.confirm) { setError('The passwords do not match.'); return }
    setBusy(true); setError(null)
    try {
      const r = await api.signup({ name: form.name, email: form.email, password: form.password,
        requested_role: form.requested_role, note: form.note || null })
      setDone(r.message)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'The request did not go through.')
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <>
        <h1 id="login-title">Request sent</h1>
        <div className="banner login-ok" role="status" style={{ margin: 0 }}>{done}</div>
        <button className="btn" type="button" onClick={onBack}>Back to sign in</button>
      </>
    )
  }

  return (
    <>
      <h1 id="login-title">Create an account</h1>
      <p className="sub" style={{ margin: 0 }}>
        An administrator reviews every request and confirms your role before you can sign in, because
        this system holds student records.
      </p>
      {error && <div className="banner critical" role="alert" style={{ margin: 0 }}>{error}</div>}
      <form onSubmit={submit} className="login-form">
        <div className="field">
          <label htmlFor="su-name">Full name</label>
          <input id="su-name" className="inp" autoComplete="name" required maxLength={120}
            value={form.name} onChange={set('name')} />
        </div>
        <div className="field">
          <label htmlFor="su-email">School email</label>
          <input id="su-email" className="inp" type="email" autoComplete="email" required maxLength={160}
            placeholder={c.signup_domains.length ? `you@${c.signup_domains[0]}` : undefined}
            value={form.email} onChange={set('email')} />
        </div>
        <div className="field">
          <label htmlFor="su-role">Your role</label>
          <select id="su-role" className="inp" value={form.requested_role} onChange={set('requested_role')}>
            {c.signup_roles.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="su-password">Password (at least 12 characters)</label>
          <input id="su-password" className="inp" type="password" autoComplete="new-password" required minLength={12}
            value={form.password} onChange={set('password')} />
        </div>
        <div className="field">
          <label htmlFor="su-confirm">Confirm password</label>
          <input id="su-confirm" className="inp" type="password" autoComplete="new-password" required
            aria-invalid={mismatch} value={form.confirm} onChange={set('confirm')} />
          {mismatch && <span className="sub" style={{ color: 'var(--critical)' }}>The passwords do not match.</span>}
        </div>
        <div className="field">
          <label htmlFor="su-note">Anything the administrator should know (optional)</label>
          <textarea id="su-note" className="inp" rows={2} maxLength={1000}
            placeholder={form.requested_role === 'teacher' ? 'e.g. I teach Algebra 1, periods 1 and 3' : undefined}
            value={form.note} onChange={set('note')} />
        </div>
        <button className="btn primary" type="submit" disabled={busy || mismatch}>
          {busy ? 'Sending…' : 'Request account'}
        </button>
      </form>
      <p className="sub login-switch">
        Already have an account? <button type="button" className="linkbtn" onClick={onBack}>Sign in</button>
      </p>
    </>
  )
}
