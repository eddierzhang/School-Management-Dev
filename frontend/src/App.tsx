import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { useApi } from './useApi'
import { StudentDrawer } from './components/StudentDrawer'
import { Agents } from './views/Agents'
import { Classes } from './views/Classes'
import { Overview } from './views/Overview'
import { Plans } from './views/Plans'
import { SkillGaps } from './views/SkillGaps'
import { Stockroom } from './views/Stockroom'
import { Strengths, Watchlist } from './views/Watchlist'
import { ErrorNote } from './components/ui'

type Tab = 'overview' | 'watchlist' | 'strengths' | 'classes' | 'skills' | 'plans'
  | 'stockroom' | 'agents'

const TAB_IDS: Tab[] = ['overview', 'watchlist', 'strengths', 'classes', 'skills', 'plans',
  'stockroom', 'agents']

/* The URL is the view: #/watchlist, #/classes, #/watchlist/S-1507 with a student
   open. A support office bookmarks the watchlist and mails a colleague a link to
   one student, so the address bar has to mean something. */
function readHash(): { tab: Tab; sid: string | null } {
  const raw = window.location.hash.replace(/^#\/?/, '')
  const [first = '', second = ''] = raw.split('/')
  const tab = (TAB_IDS as string[]).includes(first) ? (first as Tab) : 'overview'
  return { tab, sid: second ? decodeURIComponent(second) : null }
}

function writeHash(tab: Tab, sid: string | null) {
  const next = `#/${tab}${sid ? `/${encodeURIComponent(sid)}` : ''}`
  if (window.location.hash !== next) window.history.replaceState(null, '', next)
}

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'watchlist', label: 'Struggling' },
  { id: 'strengths', label: 'Excelling' },
  { id: 'classes', label: 'Classes' },
  { id: 'skills', label: 'What they struggle on' },
  { id: 'plans', label: 'Support plans' },
  { id: 'stockroom', label: 'Stockroom' },
  { id: 'agents', label: 'Agents' },
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
  const initial = readHash()
  const [tab, setTab] = useState<Tab>(initial.tab)
  const [openSid, setOpenSid] = useState<string | null>(initial.sid)
  const [refresh, setRefresh] = useState(0)
  const summary = useApi(() => api.summary(), [refresh])
  const stock = useApi(() => api.stockroomSummary(), [refresh])

  const bump = useCallback(() => setRefresh((n) => n + 1), [])

  useEffect(() => { writeHash(tab, openSid) }, [tab, openSid])

  useEffect(() => {
    const onHash = () => {
      const h = readHash()
      setTab(h.tab)
      setOpenSid(h.sid)
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
          watchlist: summary.data.needs_plan + summary.data.watch,
          strengths: summary.data.excelling,
          plans: summary.data.open_interventions,
        }
      : {}),
    ...(stock.data ? { stockroom: stock.data.needs_attention } : {}),
  }

  return (
    <>
      <header className="masthead">
        <div className="masthead-in">
          <div className="mast-id">
            <Crest />
            <div>
              <div className="mast-name">{summary.data?.school ?? 'Halverson Ridge Middle School'}</div>
              <div className="mast-sub">Student support office</div>
            </div>
          </div>
          <div className="mast-facts">
            <div className="fact"><span className="fact-k">Term</span><span className="fact-v">{summary.data?.term ?? '—'}</span></div>
            <div className="fact"><span className="fact-k">As of</span><span className="fact-v">{summary.data?.today ?? '—'}</span></div>
            <div className="fact"><span className="fact-k">Students</span><span className="fact-v">{summary.data?.students ?? '—'}</span></div>
            <div className="fact"><span className="fact-k">Graded pieces</span><span className="fact-v">{summary.data?.graded_assessments ?? '—'}</span></div>
          </div>
        </div>
      </header>

      <main className="shell">
        <nav className="tabs" role="tablist" aria-label="Support views">
          {TABS.map((t) => (
            <button
              key={t.id} className="tab" role="tab" aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              {counts[t.id] ? <span className="count">{counts[t.id]}</span> : null}
            </button>
          ))}
        </nav>

        {summary.error && <ErrorNote error={summary.error} onRetry={summary.reload} />}

        {tab === 'overview' && (
          <Overview onOpenStudent={setOpenSid} onGoto={(t) => setTab(t as Tab)} onChanged={bump} />
        )}
        {tab === 'watchlist' && <Watchlist key={refresh} onOpenStudent={setOpenSid} />}
        {tab === 'strengths' && <Strengths key={refresh} onOpenStudent={setOpenSid} />}
        {tab === 'classes' && <Classes onOpenStudent={setOpenSid} />}
        {tab === 'skills' && <SkillGaps />}
        {tab === 'plans' && <Plans onOpenStudent={setOpenSid} onChanged={bump} />}
        {tab === 'stockroom' && <Stockroom onChanged={bump} />}
        {tab === 'agents' && <Agents onChanged={bump} />}
      </main>

      {openSid && (
        <StudentDrawer sid={openSid} onClose={() => setOpenSid(null)} onChanged={bump} />
      )}
    </>
  )
}
