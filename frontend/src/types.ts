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
  /** excel_index - struggle_index, from -100 to +100 */
  standing: number
  /** a real concern and a real strength at once, which the standing score nets away */
  mixed: boolean
  band: Band
  /** What the index said; differs from `band` only while an override sets it. */
  computed_band: Band
  acknowledged: boolean
  absence_rate: number
  open_interventions: number
  top_reason: string | null
  course_count: number
  lowest_course: string | null
  lowest_pct: number | null
  strongest_course: string | null
  strongest_pct: number | null
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
  standing: number
  mixed: boolean
  band: Band
  computed_band: Band
  acknowledged: boolean
  override: ActiveOverride | null
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
  waitlist: number
  class_mean: number | null
  below_support: number
  excelling: number
  weakest_skill: string | null
  weakest_skill_mean: number | null
  description: string
  length: string
  credits: number
  prerequisite: string
  uc_approved: boolean
  extra_period: boolean
  graded: boolean
  catalog_page: number | null
  legacy_title: string
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
  stats: CourseStats | null
  assessments: CourseAssessmentRow[]
  teacher: CourseTeacher | null
  plans: CoursePlanRow[]
  supplies: CourseSupplyRow[]
}

export interface CourseStats {
  students: number
  median: number | null
  completion_rate: number | null
  late_rate: number | null
  mean_trend: number | null
  improving: number
  declining: number
  absence_rate: number | null
  needs_plan: number
  watch: number
}

export interface CourseAssessmentRow {
  id: number
  title: string
  kind: string
  skill: string
  due_on: string
  class_mean: number | null
  submitted: number
  missing: number
  late: number
}

export interface TeacherSectionRow {
  code: string
  title: string
  period: number
  room: string
  enrolled: number
  class_mean: number | null
}

export interface CourseTeacher {
  name: string
  sections: TeacherSectionRow[]
  students_taught: number
}

export interface CoursePlanRow {
  id: number
  sid: string
  student_name: string
  kind: string
  title: string
  owner: string
  status: string
}

export interface CourseSupplyRow {
  sku: string
  name: string
  on_hand: number
  par: number
  status: StockStatus
  status_label: string
  requisitioned: boolean
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
  decided_by: string | null
  /** Why it was rejected (always present on a rejection) or a note on approval. */
  decision_note: string | null
}

/* ---- history and overrides (backend/app/history.py) ---- */
export interface ActiveOverride {
  id: number
  kind: 'acknowledge' | 'set-band'
  band: Band | null
  note: string
  expires_on: string
  created_by: string
}

export interface OverrideRecord extends ActiveOverride {
  computed_band: Band
  created_at: string | null
  revoked_at: string | null
  revoked_by: string | null
  active: boolean
  label: string
}

export interface StudentSnapshot {
  on: string
  struggle_index: number
  excel_index: number
  band: Band
  absence_rate: number
  open_interventions: number
}

export interface StudentHistory {
  sid: string
  snapshots: StudentSnapshot[]
  events: { on: string; kind: string; label: string; detail: string }[]
  overrides: OverrideRecord[]
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

export interface NewInventoryItem {
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
  linked_courses: string[]
}

export interface InventoryPatch {
  on_hand?: number
  reorder_point?: number
  par?: number
  requisitioned?: boolean
}


/* ---- student documents ---- */

export interface DocEvidence {
  source: string
  detail: string
  kind: 'strand' | 'course' | 'attendance' | 'missing'
  pct?: number
  rate?: number
  concern?: boolean
}

export type Corroboration = 'agrees' | 'disagrees' | 'mixed' | 'no-evidence' | 'no-record'

export interface DocFinding {
  area: string
  type: 'need' | 'strength'
  severity: 'high' | 'medium' | 'low'
  severity_note: string | null
  quote: string
  explanation: string
  suggested_support: string
  gradebook: { verdict: Corroboration; evidence: DocEvidence[] }
}

export interface WithheldFinding {
  area?: string
  type?: string
  quote?: string
  reason: string
}

export interface StudentDocumentRow {
  id: number
  student_sid: string
  student_name: string
  filename: string
  kind: string
  pages: number | null
  chars: number
  status: 'processing' | 'done' | 'failed'
  summary: string
  chunks: number
  model: string
  duration_ms: number
  error: string | null
  needs: number
  strengths: number
  withheld: number
  uploaded_at: string | null
  analysed_at: string | null
}

export interface StudentDocumentDetail extends StudentDocumentRow {
  findings: DocFinding[]
  rejected: WithheldFinding[]
  notices: string[]
  text: string
}


/* ---- finance ---- */

export interface Commitment { source: string; sku: string; name: string; amount: number }

export interface BudgetLine {
  code: string
  name: string
  department: string
  category: string
  owner: string
  allocated: number
  transfers_in: number
  transfers_out: number
  budget: number
  spent: number
  one_time: number
  committed: number
  available: number
  used_pct: number
  projected: number
  status: StockStatus
  status_label: string
  note: string
  transaction_count: number
  commitments: Commitment[]
}

export interface Txn {
  id: number
  line: string
  line_name: string
  posted_on: string
  vendor: string
  description: string
  amount: number
  reference: string
  one_time: boolean
  review_status: 'clear' | 'flagged' | 'cleared'
  review_note: string
}

export interface BudgetTransferRow {
  id: number
  from_line: string | null
  to_line: string | null
  amount: number
  reason: string
  approved_by: string
  created_at: string | null
}

export interface BudgetLineDetail extends BudgetLine {
  transactions: Txn[]
  transfers: BudgetTransferRow[]
}

export interface Anomaly {
  rule: string
  transaction_id: number
  related_id: number | null
  line: string
  vendor: string
  amount: number
  posted_on: string
  review_status: 'clear' | 'flagged' | 'cleared'
  detail: string
}

export interface FinanceSummary {
  fiscal_year: string
  as_of: string
  elapsed_pct: number
  budget: number
  spent: number
  committed: number
  available: number
  projected: number
  lines: number
  over: number
  at_risk: number
  underspending: number
  anomalies: number
  flagged: number
  needs_attention: number
}

// ---- class demand -----------------------------------------------------------
export type DemandAction = 'open-section' | 'raise-capacity' | 'promote' | 'review' | 'none'

export interface SectionDemand {
  code: string
  teacher: string
  period: number
  room: string
  capacity: number
  enrolled: number
  waitlist: number
}

export interface ClassDemand {
  code: string
  title: string
  dept: string
  sections: SectionDemand[]
  enrolled: number
  capacity: number
  waitlist: number
  signups: number[]
  recent_signups: number
  prior_signups: number
  trend: 'rising' | 'falling' | 'level'
  fill: number
  pressure: number
  velocity: number
  score: number
  kind: StatusKind
  label: string
  action: DemandAction
  reasons: string[]
}

export interface DemandReport {
  formula: string
  bands: { min: number; kind: StatusKind; label: string }[]
  classes: ClassDemand[]
}

export interface Openings {
  period: number
  free_rooms: string[]
  free_teachers: string[]
}

export interface NewSection {
  period: number
  room: string
  teacher?: string | null
  capacity?: number | null
  move_from_waitlist?: number
}

export interface NewClass {
  code: string
  title: string
  dept: string
  teacher: string
  period: number
  room: string
  capacity: number
  description?: string
  length?: 'year' | 'semester'
  credits?: number
  prerequisite?: string
}

export interface Opened {
  course: CourseRow
  moved_from_waitlist: number
  message: string
}

// ---- schedule ---------------------------------------------------------------
export interface SectionSlot {
  code: string
  title: string
  dept: string
  teacher: string
  room: string
  period: number              // 0 = outside the timetable
  length: string
  credits: number
  enrolled: number
  capacity: number
  waitlist: number
  base_code: string
}

export interface SchoolSchedule {
  periods: number[]
  sections: SectionSlot[]
  rooms: string[]
  teachers: string[]
  clashes: { kind: 'room' | 'teacher'; who: string; period: number; sections: string[] }[]
  student_clashes: { sid: string; name: string; grade: number; period: number; sections: string[] }[]
  students_with_clashes: number
}

export interface StudentPeriod {
  period: number
  enrolled: SectionSlot[]
  waitlisted: SectionSlot[]
  clash: boolean
}

export interface StudentSchedule {
  sid: string
  name: string
  grade: number
  homeroom: string
  periods: StudentPeriod[]
  classes: number
  credits: number
  free_periods: number[]
  clashes: number
  waitlisted: number
}

// ---- class improvement plans ------------------------------------------------
export type ClassStatus = 'needs-plan' | 'watch' | 'strong' | 'no-data'

export interface ClassPerformance {
  code: string
  title: string
  dept: string
  teacher: string
  students: number
  mean: number | null
  median: number | null
  below_line: number
  completion: number | null
  trend: number | null
  improving: number
  declining: number
  needs_plan: number
  strands: { strand: string; mean: number; below_line: number; cohort: number; share_below: number }[]
  kinds: { kind: string; mean: number | null; handed_in: number }[]
  status: ClassStatus
  issues: string[]
}

export interface ClassPlan {
  id: number
  course_code: string
  title: string
  diagnosis: string
  focus_strands: string[]
  actions: string[]
  goal: string
  owner: string
  status: 'active' | 'completed' | 'retired'
  outcome: string | null
  opened_on: string
  review_on: string | null
  closed_on: string | null
  run_id: number | null
  progress: { measure: string; baseline: number | null; now: number | null; change: number | null }[]
}

export interface PlanDraft {
  id: number
  run_id: number | null
  summary: string
  payload: { course_code: string; title: string; diagnosis: string; focus_strands: string[]; actions: string[]; goal: string }
  created_at: string | null
}

export interface DraftRun {
  id: number
  status: 'running' | 'done' | 'failed'
  summary: string
  error: string | null
  steps_used: number
  duration_ms: number
  proposals: number
  started_at: string | null
}

export interface ClassImprovement {
  performance: ClassPerformance
  plans: ClassPlan[]
  drafts: PlanDraft[]
  latest_run: DraftRun | null
}

export interface ClassNeedRow {
  code: string
  title: string
  teacher: string
  status: ClassStatus
  mean: number | null
  issues: string[]
  active_plan: string | null
  drafts_waiting: number
}

// ---- study plans (one student, one class) -----------------------------------
export interface StudyClassRow {
  code: string
  title: string
  teacher: string
  pct: number
  class_pct: number | null
  needs_plan: boolean
  findings: string[]
  active_plan_id: number | null
  drafts_waiting: number
  latest_run: DraftRun | null
}

export interface StudyProgressRow {
  measure: string
  baseline: number | null
  now: number | null
  change: number | null
  unit: '%' | ''
}

export interface StudyPlan {
  id: number
  student_sid: string
  course_code: string
  title: string
  diagnosis: string
  focus_strands: string[]
  sessions: string[]
  catch_up: { id: number; title: string; due_on: string }[]
  goal: string
  owner: string
  status: 'active' | 'completed' | 'retired'
  outcome: string | null
  opened_on: string
  review_on: string | null
  closed_on: string | null
  run_id: number | null
  progress: StudyProgressRow[]
}

export interface StudyDraft {
  id: number
  run_id: number | null
  summary: string
  payload: {
    student_sid: string; course_code: string; title: string; diagnosis: string
    focus_strands: string[]; sessions: string[]; catch_up_assignments: number[]; goal: string
  }
  created_at: string | null
}

export interface StudentStudy {
  sid: string
  classes: StudyClassRow[]
  plans: StudyPlan[]
  drafts: StudyDraft[]
}

export interface ClassWorkAssignment {
  id: number
  title: string
  kind: string
  strand: string
  due_on: string
  pct: number | null
  class_pct: number | null
  late: boolean
}

export interface ClassWork {
  sid: string
  course_code: string
  course_title: string
  pct: number
  class_pct: number | null
  assignments: ClassWorkAssignment[]
  strands: {
    strand: string; pct: number; handed_in_pct: number | null; class_pct: number | null
    graded: number; missing: number
  }[]
  kinds: { kind: string; pct: number | null; handed_in: number; due: number }[]
  findings: { code: string; text: string; strand: string | null }[]
}

// ---- budget needs, new lines and revisions ----------------------------------
export interface LineNeed {
  code: string
  name: string
  status_label: string
  overrun: number
  unfunded_stock: number
  need: number
  reasons: string[]
}

export interface FinanceNeeds {
  needs: LineNeed[]
  room: { code: string; name: string; can_give: number }[]
}

export interface BudgetMove {
  from_line: string
  to_line: string
  amount: number
}

// --- accounts and the audit log (backend/app/routers/auth.py, admin.py) ---
export type Role = 'admin' | 'counselor' | 'teacher' | 'registrar' | 'business'

export interface Me {
  id: number
  email: string
  name: string
  role: Role
  role_label: string
  teacher_name: string | null
  permissions: string[]
  /** Optional modules turned on for this deployment (HR_MODULES). */
  modules: string[]
}

export interface AuthConfig {
  password_login: boolean
  oidc: boolean
  oidc_label: string
  school: string
}

export interface AdminUser {
  id: number
  email: string
  name: string
  role: Role
  role_label: string
  teacher_name: string | null
  active: boolean
  has_password: boolean
  created_at: string | null
  last_login_at: string | null
}

export interface NewUser {
  email: string
  name: string
  role: Role
  teacher_name?: string | null
  password?: string | null
}

export interface RolesInfo {
  roles: { role: Role; label: string; permissions: string[] }[]
  permissions: Record<string, string>
}

export interface AuditEvent {
  id: number
  at: string
  actor_email: string
  actor_role: string
  action: string
  status: number | null
  entity_type: string | null
  entity_id: string | null
  path: string
  ip: string
  request_id: string
  detail: Record<string, string>
}

export interface AuditPage {
  events: AuditEvent[]
  next_before_id: number | null
}
