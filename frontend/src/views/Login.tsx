import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api'
import { useApi } from '../useApi'

const ERRORS: Record<string, string> = {
  'not-registered': 'Your school account signed in, but it has no access here. Ask an administrator to add you.',
  'sign-in-failed': 'Signing in with your school account did not complete. Try again.',
  'provider-unavailable': 'The school sign-in service could not be reached. Try again shortly.',
}

export function Login({ onSignedIn }: { onSignedIn: () => void }) {
  const config = useApi(() => api.authConfig(), [])
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

  const c = config.data
  return (
    <div className="login-wrap">
      <main className="login-card" aria-labelledby="login-title">
        <div className="eyebrow">{c?.school ?? 'Halverson Ridge High School'}</div>
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
      </main>
    </div>
  )
}
