import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { useApi } from './useApi'
import { StudentDrawer } from './components/StudentDrawer'
import { Agents } from './views/Agents'
import { Classes } from './views/Classes'
import { Schedule } from './views/Schedule'
import { Demand } from './views/Demand'
import { Overview } from './views/Overview'
import { Plans } from './views/Plans'
import { SkillGaps } from './views/SkillGaps'
import { Stockroom } from './views/Stockroom'
import { Finance } from './views/Finance'
import { Students, type Group } from './views/Students'
import { ErrorNote } from './components/ui'
import { useAuth } from './auth'
import { Admin } from './views/Admin'

type Tab = 'overview' | 'students' | 'classes' | 'schedule' | 'demand' | 'skills' | 'plans'
  | 'stockroom' | 'finance' | 'agents' | 'admin'

const TAB_IDS: Tab[] = ['overview', 'students', 'classes', 'schedule', 'demand', 'skills', 'plans',
  'stockroom', 'finance', 'agents', 'admin']

/* The URL is the view: #/students, #/classes, #/students/S-1507 with a student
   open. A support office bookmarks the list and mails a colleague a link to
   one student, so the address bar has to mean something. */

// The struggling and excelling tabs were merged into #/students; old bookmarks
// still land there, pre-filtered to the list they used to show.
const LEGACY_TABS: Record<string, Group> = { watchlist: 'concern', strengths: 'strength' }

function readHash(): { tab: Tab; sid: string | null; group?: Group } {
  const raw = window.location.hash.replace(/^#\/?/, '')
  const [first = '', second = ''] = raw.split('/')
  const sid = second ? decodeURIComponent(second) : null
  if (first in LEGACY_TABS) return { tab: 'students', sid, group: LEGACY_TABS[first] }
  const tab = (TAB_IDS as string[]).includes(first) ? (first as Tab) : 'overview'
  return { tab, sid }
}

function writeHash(tab: Tab, sid: string | null) {
  const next = `#/${tab}${sid ? `/${encodeURIComponent(sid)}` : ''}`
  if (window.location.hash !== next) window.history.replaceState(null, '', next)
}

/* Each tab names the permission it needs; a tab the signed-in person cannot use
   is not shown. The API enforces the same rules whatever the interface shows. */
const TABS: { id: Tab; label: string; needs: string }[] = [
  { id: 'overview', label: 'Overview', needs: 'students.read' },
  { id: 'students', label: 'Students', needs: 'students.read' },
  { id: 'classes', label: 'Classes', needs: 'students.read' },
  { id: 'schedule', label: 'Schedule', needs: 'schedule.read' },
  { id: 'demand', label: 'Class demand', needs: 'courses.write' },
  { id: 'skills', label: 'What they struggle on', needs: 'students.read' },
  { id: 'plans', label: 'Support plans', needs: 'students.read' },
  { id: 'stockroom', label: 'Stockroom', needs: 'inventory.read' },
  { id: 'finance', label: 'Finance', needs: 'finance.read' },
  { id: 'agents', label: 'Agents', needs: 'agents.read' },
  { id: 'admin', label: 'Admin', needs: 'audit.read' },
]

function Crest() {
  return (
    <svg width="34" height="34" viewBox="0 0 32 32" aria-hidden="true" style={{ flex: 'none' }}>
      <path d="M16 2 3 7v10.5C3 24 9 29.3 16 31c7-1.7 13-7 13-13.5V7L16 2Z" fill="none" stroke="var(--accent)" strokeWidth="1.6" />
      <path d="M8.5 13.5h15M8.5 18h15" stroke="var(--accent)" strokeWidth="1.3" opacity=".55" />
      <path d="M16 9.2 10 11.6l6 2.4 6-2.4-6-2.4Z" fill="var(--accent)" />
      <path d="M16 22.8V16" stroke="var(--accent)" strokeWidth="1.6" />
    </svg>
  )
}

export default function App() {
  const { me, can, signOut } = useAuth()
  const tabs = TABS.filter((t) => can(t.needs))
  const initial = readHash()
  const allowed = (t: Tab) => tabs.some((x) => x.id === t)
  const [tab, setTabRaw] = useState<Tab>(allowed(initial.tab) ? initial.tab : tabs[0]?.id ?? 'overview')
  const setTab = useCallback((t: Tab) => setTabRaw(allowed(t) ? t : tabs[0]?.id ?? 'overview'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [me.id])
  // On the classes tab the second URL segment is a class code (#/classes/MAT-150);
  // everywhere else it is the open student.
  const [openSid, setOpenSid] = useState<string | null>(initial.tab === 'classes' ? null : initial.sid)
  const [openCode, setOpenCode] = useState<string | null>(initial.tab === 'classes' ? initial.sid : null)
  const [studentGroup, setStudentGroup] = useState<Group>(initial.group ?? 'all')
  const [refresh, setRefresh] = useState(0)
  const none = () => Promise.resolve(null)
  const summary = useApi(() => (can('students.read') ? api.summary() : none()), [refresh])
  const stock = useApi(() => (can('inventory.read') ? api.stockroomSummary() : none()), [refresh])
  const money = useApi(() => (can('finance.read') ? api.financeSummary() : none()), [refresh])

  const bump = useCallback(() => setRefresh((n) => n + 1), [])

  useEffect(() => { writeHash(tab, tab === 'classes' ? openCode : openSid) }, [tab, openSid, openCode])

  useEffect(() => {
    const onHash = () => {
      const h = readHash()
      setTab(h.tab)
      if (h.group) setStudentGroup(h.group)
      if (h.tab === 'classes') { setOpenCode(h.sid); setOpenSid(null) } else setOpenSid(h.sid)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpenSid(null) }
    window.addEventListener('hashchange', onHash)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('hashchange', onHash)
      window.removeEventListener('keydown', onKey)
    }
  }, [])

  const counts: Partial<Record<Tab, number>> = {
    ...(summary.data
      ? {
          students: summary.data.students,
          plans: summary.data.open_interventions,
        }
      : {}),
    ...(stock.data ? { stockroom: stock.data.needs_attention } : {}),
    ...(money.data ? { finance: money.data.needs_attention } : {}),
  }

  return (
    <>
      <header className="masthead">
        <div className="masthead-in">
          <div className="mast-id">
            <Crest />
            <div>
              <div className="mast-name">{summary.data?.school ?? 'Halverson Ridge High School'}</div>
              <div className="mast-sub">Student support office</div>
            </div>
          </div>
          <div className="mast-facts">
            <div className="fact"><span className="fact-k">Term</span><span className="fact-v">{summary.data?.term ?? '—'}</span></div>
            <div className="fact"><span className="fact-k">As of</span><span className="fact-v">{summary.data?.today ?? '—'}</span></div>
            <div className="fact"><span className="fact-k">Students</span><span className="fact-v">{summary.data?.students ?? '—'}</span></div>
            <div className="fact"><span className="fact-k">Graded pieces</span><span className="fact-v">{summary.data?.graded_assessments ?? '—'}</span></div>
            <div className="fact mast-user">
              <span className="fact-k">{me.role_label}</span>
              <span className="fact-v">
                {me.name}{' '}
                <button className="btn sm ghost" onClick={() => void signOut()}>Sign out</button>
              </span>
            </div>
          </div>
        </div>
      </header>

      <main className="shell">
        <nav className="tabs" role="tablist" aria-label="Support views">
          {tabs.map((t) => (
            <button
              key={t.id} className="tab" role="tab" aria-selected={tab === t.id}
              onClick={() => { setTab(t.id); if (t.id === 'classes') setOpenCode(null) }}
            >
              {t.label}
              {counts[t.id] ? <span className="count">{counts[t.id]}</span> : null}
            </button>
          ))}
        </nav>

        {summary.error && <ErrorNote error={summary.error} onRetry={summary.reload} />}

        {tab === 'overview' && (
          <Overview onOpenStudent={setOpenSid} onChanged={bump}
            onGoto={(t) => {
              if (t in LEGACY_TABS) { setStudentGroup(LEGACY_TABS[t]!); setTab('students') } else setTab(t as Tab)
            }} />
        )}
        {tab === 'students' && (
          <Students refresh={refresh} group={studentGroup} onGroup={setStudentGroup} onOpenStudent={setOpenSid} />
        )}
        {tab === 'schedule' && <Schedule key={refresh} onOpenStudent={setOpenSid} />}
        {tab === 'classes' && (
          <Classes key={refresh} code={openCode} onOpenStudent={setOpenSid}
            onOpenClass={(code) => { setOpenCode(code); window.scrollTo({ top: 0 }) }} />
        )}
        {tab === 'demand' && <Demand onChanged={bump} />}
        {tab === 'skills' && <SkillGaps />}
        {tab === 'plans' && <Plans onOpenStudent={setOpenSid} onChanged={bump} />}
        {tab === 'stockroom' && <Stockroom onChanged={bump} />}
        {tab === 'finance' && <Finance onChanged={bump} />}
        {tab === 'agents' && <Agents onChanged={bump} />}
        {tab === 'admin' && <Admin />}
        {tabs.length === 0 && (
          <div className="empty">
            <h2>Your account has no access yet</h2>
            <p>Ask an administrator to give it a role.</p>
          </div>
        )}
      </main>

      {openSid && (
        <StudentDrawer sid={openSid} onClose={() => setOpenSid(null)} onChanged={bump} />
      )}
    </>
  )
}
