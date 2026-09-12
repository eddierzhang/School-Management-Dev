import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from './api'

interface State<T> { data: T | null; error: string | null; loading: boolean }

/** Fetch-on-mount with a manual reload, and no setState after unmount. */
export function useApi<T>(fn: () => Promise<T>, deps: readonly unknown[] = []) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true })
  const alive = useRef(true)
  const [nonce, setNonce] = useState(0)
  const reload = useCallback(() => setNonce((n) => n + 1), [])

  useEffect(() => {
    alive.current = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fn()
      .then((data) => { if (alive.current) setState({ data, error: null, loading: false }) })
      .catch((e: unknown) => {
        const msg = e instanceof ApiError ? e.message : 'Something went wrong loading this view.'
        if (alive.current) setState({ data: null, error: msg, loading: false })
      })
    return () => { alive.current = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  return { ...state, reload }
}
