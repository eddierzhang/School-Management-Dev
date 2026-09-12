import type {
  CourseDetail, CourseRow, Intervention, NewIntervention,
  Recommendation, SkillGap, StudentDetail, StudentRow, Summary,
} from './types'

const BASE = '/api'

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the support API. Is the backend running on port 8000?')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) detail = body.detail[0].msg
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const qs = (params: Record<string, string | number | boolean | undefined>) => {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  summary: () => req<Summary>('/summary'),
  students: (p: { band?: string; grade?: number; course?: string; q?: string; sort?: string } = {}) =>
    req<StudentRow[]>('/students' + qs(p)),
  student: (sid: string) => req<StudentDetail>(`/students/${encodeURIComponent(sid)}`),
  courses: () => req<CourseRow[]>('/courses'),
  course: (code: string) => req<CourseDetail>(`/courses/${encodeURIComponent(code)}`),
  watchlist: (limit = 40, includeWatch = true) =>
    req<StudentDetail[]>('/watchlist' + qs({ limit, include_watch: includeWatch })),
  strengths: (limit = 40) => req<StudentDetail[]>('/strengths' + qs({ limit })),
  skillGaps: (limit = 60) => req<SkillGap[]>('/skill-gaps' + qs({ limit })),
  recommendations: (priority?: number) => req<Recommendation[]>('/recommendations' + qs({ priority })),
  interventions: (status?: string) => req<Intervention[]>('/interventions' + qs({ status })),
  createIntervention: (body: NewIntervention) =>
    req<Intervention>('/interventions', { method: 'POST', body: JSON.stringify(body) }),
  updateIntervention: (id: number, body: Partial<Pick<Intervention, 'status' | 'outcome' | 'owner'>>) =>
    req<Intervention>(`/interventions/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteIntervention: (id: number) => req<void>(`/interventions/${id}`, { method: 'DELETE' }),
}
