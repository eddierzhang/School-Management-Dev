/** Mirrors backend/app/schemas.py. One contract, typed on both sides. */

export type Band = 'needs-plan' | 'watch' | 'excelling' | 'steady'
export type StatusKind = 'good' | 'warning' | 'serious' | 'critical' | 'neutral' | 'accent'

export interface Reason {
  code: string
  label: string
  detail: string
  kind: 'concern' | 'strength'
}

export interface SkillMastery {
  skill: string
  pct: number
  graded: number
  missing: number
  course_code: string
}

export interface CourseSignal {
  course_code: string
  course_title: string
  dept: string
  teacher: string
  pct: number
  recent_pct: number | null
  prior_pct: number | null
  delta: number
  graded_items: number
  missing: number
  missing_rate: number
  completion: number
  spread: number
  struggle_index: number
  excel_index: number
  skills: SkillMastery[]
}

export interface Recommendation {
  code: string
  title: string
  rationale: string
  kind: string
  priority: number
  course_code: string | null
  suggested_owner: string
}

export interface Intervention {
  id: number
  student_sid: string
  student_name: string
  course_code: string | null
  kind: string
  title: string
  rationale: string
  owner: string
  status: 'active' | 'completed' | 'declined'
  opened_on: string
  review_on: string | null
  outcome: string | null
}

export interface StudentRow {
  sid: string
  name: string
  grade: number
  homeroom: string
  struggle_index: number
  excel_index: number
  band: Band
  absence_rate: number
  open_interventions: number
  top_reason: string | null
  course_count: number
  lowest_course: string | null
  lowest_pct: number | null
}

export interface StudentDetail {
  sid: string
  name: string
  grade: number
  homeroom: string
  guardian_name: string | null
  guardian_email: string | null
  struggle_index: number
  excel_index: number
  band: Band
  days_counted: number
  absences: number
  tardies: number
  absence_rate: number
  tardy_rate: number
  courses: CourseSignal[]
  reasons: Reason[]
  weakest_skills: SkillMastery[]
  strongest_skills: SkillMastery[]
  recommendations: Recommendation[]
  interventions: Intervention[]
}

export interface CourseRow {
  code: string
  title: string
  dept: string
  teacher: string
  period: number
  room: string
  enrolled: number
  capacity: number
  class_mean: number | null
  below_support: number
  excelling: number
  weakest_skill: string | null
  weakest_skill_mean: number | null
}

export interface CourseStudentRow {
  sid: string
  name: string
  grade: number
  pct: number
  delta: number
  missing: number
  graded_items: number
  struggle_index: number
  excel_index: number
}

export interface SkillGap {
  course_code: string
  course_title: string
  dept: string
  teacher: string
  skill: string
  class_mean: number
  students_below: number
  cohort: number
  share_below: number
}

export interface CourseDetail {
  course: CourseRow
  students: CourseStudentRow[]
  skills: SkillGap[]
  distribution: { label: string; count: number }[]
}

export interface Summary {
  school: string
  term: string
  today: string
  students: number
  courses: number
  graded_assessments: number
  bands: { band: string; count: number }[]
  needs_plan: number
  watch: number
  excelling: number
  steady: number
  open_interventions: number
  unaddressed: number
  mean_attendance: number
  top_skill_gaps: SkillGap[]
}

export interface NewIntervention {
  student_sid: string
  kind: string
  title: string
  rationale?: string
  course_code?: string | null
  owner?: string
  review_on?: string | null
}


/* ---- agent fleet ---- */

export interface OllamaHealth {
  reachable: boolean
  error: string | null
  url?: string
  model: string
  models: string[]
  model_installed?: boolean
  capabilities?: string[]
  can_run_agents: boolean
}

export interface AgentTool {
  name: string
  description: string
  proposes: string | null
}

export interface AgentInfo {
  name: string
  title: string
  domain: string
  default_task: string
  tools: AgentTool[]
}

export interface Fleet {
  runtime: OllamaHealth
  agents: AgentInfo[]
}

export interface TranscriptCall {
  tool: string
  arguments: unknown
  ok?: boolean
  result?: string
  error?: string
  repeat?: boolean
}

export interface TranscriptStep {
  step: number | string   // 0 = seeded opening read, 'harvest' = the constrained-JSON pass
  thinking?: string
  said?: string
  ms: number
  recovered_from_text?: boolean
  nudged?: boolean
  calls: TranscriptCall[]
}

export interface AgentRun {
  id: number
  agent: string
  model: string
  prompt: string
  status: 'running' | 'done' | 'failed'
  summary: string
  steps_used: number
  tool_errors: number
  duration_ms: number
  error: string | null
  started_at: string | null
  finished_at: string | null
  proposals: number
  transcript?: TranscriptStep[]
}

export interface ProposalRow {
  id: number
  run_id: number | null
  agent: string
  kind: string
  summary: string
  reason: string
  payload: Record<string, unknown>
  evidence: unknown[]
  status: 'pending' | 'approved' | 'rejected' | 'failed'
  result: string | null
  created_at: string | null
  decided_at: string | null
}


/* ---- stockroom ---- */

export type StockStatus = 'critical' | 'serious' | 'warning' | 'good'

export interface LinkedCourse {
  code: string
  title: string
  enrolled: number
}

export interface InventoryRow {
  sku: string
  name: string
  category: string
  unit: string
  on_hand: number
  reorder_point: number
  par: number
  location: string
  supplier: string
  unit_cost: number
  last_counted: string | null
  linked_courses: string[]
  requisitioned: boolean
  status: StockStatus
  status_label: string
  ratio: number
  short_by: number
  cost_to_par: number
  students_affected: number
  days_since_count: number | null
}

export interface InventoryDetail extends InventoryRow {
  value_on_hand: number
  classes: LinkedCourse[]
}

export interface RequisitionSupplier {
  supplier: string
  lines: InventoryRow[]
  cost: number
}

export interface Requisition {
  lines: number
  cost: number
  by_supplier: RequisitionSupplier[]
}

export interface StockroomSummary {
  items: number
  needs_attention: number
  below_reorder: number
  on_requisition: number
  value_on_hand: number
  cost_to_par: number
  categories: string[]
}

export interface InventoryPatch {
  on_hand?: number
  reorder_point?: number
  par?: number
  requisitioned?: boolean
}
