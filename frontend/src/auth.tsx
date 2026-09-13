import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ApiError, SIGNED_OUT_EVENT } from './api'
import type { Me } from './types'

/* Who is signed in, and what they may do.

   The permissions come from the server, which enforces every one of them; hiding
   a button here is only so nobody is offered something the API would refuse. */

interface AuthState {
  me: Me
  can: (permission: string) => boolean
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside <AuthGate>')
  return ctx
}

/** Shorthand for components that only need one check. */
export function useCan(permission: string): boolean {
  return useAuth().can(permission)
}

export function AuthGate({ signIn, children }: {
  signIn: (onSignedIn: () => void) => ReactNode
  children: ReactNode
}) {
  const [me, setMe] = useState<Me | null>(null)
  const [checked, setChecked] = useState(false)
  const [unreachable, setUnreachable] = useState<string | null>(null)

  const load = useCallback(() => {
    api.me()
      .then((m) => { setMe(m); setUnreachable(null) })
      .catch((e: unknown) => {
        setMe(null)
        if (e instanceof ApiError && e.status !== 401) setUnreachable(e.message)
      })
      .finally(() => setChecked(true))
  }, [])

  useEffect(() => { load() }, [load])

  // Any request that comes back 401 means the session ended (expired, signed out
  // elsewhere, or the account was changed): drop straight to the sign-in screen.
  useEffect(() => {
    const onSignedOut = () => setMe(null)
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut)
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut)
  }, [])

  const signOut = useCallback(async () => {
    try { await api.logout() } finally { setMe(null) }
  }, [])

  if (!checked) return null
  if (unreachable && !me) {
    return (
      <div className="login-wrap">
        <div className="login-card">
          <h1>Cannot reach the server</h1>
          <p className="sub">{unreachable}</p>
          <button className="btn" onClick={load}>Try again</button>
        </div>
      </div>
    )
  }
  if (!me) return <>{signIn(load)}</>

  const perms = new Set(me.permissions)
  return (
    <AuthContext.Provider value={{ me, can: (p) => perms.has(p), signOut }}>
      {children}
    </AuthContext.Provider>
  )
}
