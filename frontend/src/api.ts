import type {
  BudgetMove, FinanceNeeds,
  ClassImprovement, ClassNeedRow, ClassPlan, DraftRun,
  SchoolSchedule, StudentSchedule,
  DemandReport, NewClass, NewSection, Opened, Openings,
  AgentRun, CourseDetail, CourseRow, Fleet, Intervention, InventoryDetail, InventoryPatch,
  InventoryRow, NewIntervention, ProposalRow, Recommendation, Requisition, SkillGap,
  StockroomSummary, StudentDetail, Anomaly, BudgetLine, BudgetLineDetail, BudgetTransferRow,
  FinanceSummary, Txn, StudentDocumentDetail, StudentDocumentRow, StudentRow, Summary,
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
    const isForm = init?.body instanceof FormData
    res = await fetch(BASE + path, {
      ...init,
      headers: isForm ? (init?.headers ?? {}) : { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
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
  studentSchedule: (sid: string) => req<StudentSchedule>(`/students/${encodeURIComponent(sid)}/schedule`),
  schedule: () => req<SchoolSchedule>('/schedule'),
  courses: () => req<CourseRow[]>('/courses'),
  course: (code: string) => req<CourseDetail>(`/courses/${encodeURIComponent(code)}`),
  improvement: (code: string) => req<ClassImprovement>(`/courses/${encodeURIComponent(code)}/improvement`),
  improvementAll: () => req<ClassNeedRow[]>('/improvement'),
  draftClassPlan: (code: string, note?: string) =>
    req<DraftRun>(`/courses/${encodeURIComponent(code)}/improvement/draft`, {
      method: 'POST', body: JSON.stringify({ note: note ?? null }),
    }),
  closeClassPlan: (id: number, status: 'completed' | 'retired', outcome?: string) =>
    req<ClassPlan>(`/improvement-plans/${id}`, { method: 'PATCH', body: JSON.stringify({ status, outcome: outcome ?? null }) }),
  demand: () => req<DemandReport>('/courses/demand'),
  openings: (period: number) => req<Openings>('/courses/openings' + qs({ period })),
  openClass: (body: NewClass) =>
    req<Opened>('/courses', { method: 'POST', body: JSON.stringify(body) }),
  openSection: (code: string, body: NewSection) =>
    req<Opened>(`/courses/${encodeURIComponent(code)}/sections`, { method: 'POST', body: JSON.stringify(body) }),
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

  // --- student documents ---
  documents: (sid: string) =>
    req<StudentDocumentRow[]>(`/students/${encodeURIComponent(sid)}/documents`),
  document: (id: number) => req<StudentDocumentDetail>(`/documents/${id}`),
  uploadDocument: (sid: string, file: File, kind: string) => {
    const body = new FormData()
    body.append('file', file)
    body.append('kind', kind)
    return req<StudentDocumentRow>(`/students/${encodeURIComponent(sid)}/documents`, { method: 'POST', body })
  },
  reanalyseDocument: (id: number) =>
    req<StudentDocumentRow>(`/documents/${id}/analyze`, { method: 'POST' }),
  deleteDocument: (id: number) => req<void>(`/documents/${id}`, { method: 'DELETE' }),

  // --- finance ---
  financeSummary: () => req<FinanceSummary>('/finance/summary'),
  budgetLines: () => req<BudgetLine[]>('/finance/lines'),
  budgetLine: (code: string) => req<BudgetLineDetail>(`/finance/lines/${encodeURIComponent(code)}`),
  anomalies: () => req<Anomaly[]>('/finance/anomalies'),
  flaggedTransactions: () => req<Txn[]>('/finance/transactions?review_status=flagged'),
  recordTransaction: (body: {
    line_code: string; vendor: string; description: string; amount: number
    posted_on?: string; reference?: string; one_time?: boolean
  }) => req<Txn>('/finance/transactions', { method: 'POST', body: JSON.stringify(body) }),
  reviewTransaction: (id: number, review_status: Txn['review_status'], review_note = '') =>
    req<Txn>(`/finance/transactions/${id}`, {
      method: 'PATCH', body: JSON.stringify({ review_status, review_note }),
    }),
  transfer: (body: { from_line: string; to_line: string; amount: number; reason: string }) =>
    req<BudgetTransferRow>('/finance/transfers', { method: 'POST', body: JSON.stringify(body) }),
  financeNeeds: () => req<FinanceNeeds>('/finance/needs'),
  openBudgetLine: (body: {
    code: string; name: string; department: string; category: string; owner?: string
    from_line: string; amount: number; reason: string
  }) => req<BudgetLine>('/finance/lines', { method: 'POST', body: JSON.stringify(body) }),
  reviseBudget: (moves: BudgetMove[], reason: string) =>
    req<{ moved: number; transfers: BudgetTransferRow[] }>('/finance/revisions', {
      method: 'POST', body: JSON.stringify({ moves, reason }),
    }),

  // --- stockroom ---
  inventory: (p: { category?: string; needs_attention?: boolean; q?: string } = {}) =>
    req<InventoryRow[]>('/inventory' + qs(p)),
  stockroomSummary: () => req<StockroomSummary>('/inventory/summary'),
  requisition: () => req<Requisition>('/inventory/requisition'),
  requisitionAllLow: () =>
    req<Requisition>('/inventory/requisition/low', { method: 'POST' }),
  item: (sku: string) => req<InventoryDetail>(`/inventory/${encodeURIComponent(sku)}`),
  patchItem: (sku: string, body: InventoryPatch) =>
    req<InventoryDetail>(`/inventory/${encodeURIComponent(sku)}`, {
      method: 'PATCH', body: JSON.stringify(body),
    }),
  countItem: (sku: string, on_hand: number) =>
    req<InventoryDetail>(`/inventory/${encodeURIComponent(sku)}/count`, {
      method: 'POST', body: JSON.stringify({ on_hand }),
    }),

  // --- agent fleet ---
  fleet: () => req<Fleet>('/agents'),
  runAgent: (name: string, task?: string) =>
    req<AgentRun>(`/agents/${encodeURIComponent(name)}/run`, {
      method: 'POST', body: JSON.stringify({ task: task ?? null }),
    }),
  runs: (agent?: string) => req<AgentRun[]>('/agents/runs' + qs({ agent })),
  run: (id: number) => req<AgentRun>(`/agents/runs/${id}`),
  proposals: (status?: string) => req<ProposalRow[]>('/agents/proposals' + qs({ status })),
  approveProposal: (id: number) =>
    req<{ applied: boolean; result: string; proposal: ProposalRow }>(
      `/agents/proposals/${id}/approve`, { method: 'POST' }),
  rejectProposal: (id: number, note?: string) =>
    req<{ rejected: boolean; proposal: ProposalRow }>(
      `/agents/proposals/${id}/reject`, { method: 'POST', body: JSON.stringify({ note: note ?? null }) }),
}
