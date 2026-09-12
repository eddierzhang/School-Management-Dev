import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type {
  Corroboration, DocFinding, Recommendation, StatusKind, StudentDocumentDetail, StudentDocumentRow,
} from '../types'
import { ErrorNote, Pill } from './ui'

const KINDS: [string, string][] = [
  ['teacher-note', 'Teacher note'],
  ['report-card', 'Report card'],
  ['assessment', 'Test or assessment'],
  ['essay', 'Student work or essay'],
  ['counselor-note', 'Counselor note'],
  ['other', 'Something else'],
]

const PLAN_KINDS = ['tutoring', 'homework-recovery', 'check-in', 'attendance-plan', 'family-contact', 'enrichment']

const VERDICT: Record<Corroboration, [StatusKind, string]> = {
  agrees: ['good', 'Gradebook agrees'],
  disagrees: ['serious', 'Gradebook disagrees'],
  mixed: ['warning', 'Gradebook is mixed'],
  'no-evidence': ['neutral', 'Nothing in the gradebook on this'],
  'no-record': ['neutral', 'No gradebook record'],
}

const SEVERITY: Record<string, StatusKind> = { high: 'critical', medium: 'serious', low: 'warning' }

/** A finding becomes a support plan the same way a recommendation does — the
    quotation travels with it as the rationale, so the plan says why it exists. */
function seedFrom(doc: StudentDocumentRow, f: DocFinding): Recommendation {
  const course = f.gradebook.evidence
    .map((e) => e.source.match(/\(([A-Z]{2,4}-\d{2,3})\)/)?.[1])
    .find(Boolean) ?? null
  const kind = PLAN_KINDS.includes(f.suggested_support)
    ? f.suggested_support
    : f.type === 'strength' ? 'enrichment' : 'check-in'
  const label = kind === 'enrichment' ? 'Build on' : 'Support with'
  return {
    code: 'document',
    title: `${label} ${f.area}`,
    rationale: `From "${doc.filename}": “${f.quote}”${f.explanation ? ` — ${f.explanation}` : ''}`,
    kind,
    priority: f.severity === 'high' ? 1 : f.severity === 'medium' ? 2 : 3,
    course_code: course,
    suggested_owner: 'Support office',
  }
}

function Finding({ doc, f, onOpenPlan }: {
  doc: StudentDocumentRow; f: DocFinding; onOpenPlan: (seed: Recommendation) => void
}) {
  const [kind, label] = VERDICT[f.gradebook.verdict]
  return (
    <div className={`finding ${f.type}`}>
      <div style={{ display: 'flex', gap: 7, alignItems: 'center', flexWrap: 'wrap' }}>
        {f.type === 'need'
          ? <Pill kind={SEVERITY[f.severity] ?? 'serious'}>{f.severity} need</Pill>
          : <Pill kind="good">strength</Pill>}
        <b style={{ fontSize: 13 }}>{f.area}</b>
      </div>
      <blockquote className="quote">“{f.quote}”</blockquote>
      {f.explanation && <div style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>{f.explanation}</div>}
      {f.severity_note && <div className="sub">{f.severity_note}</div>}
      <div style={{ display: 'flex', gap: 7, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <Pill kind={kind}>{label}</Pill>
        {f.gradebook.evidence.length > 0 && (
          <span className="sub">
            {f.gradebook.evidence.map((e) => `${e.source} ${e.detail}`).join(' · ')}
          </span>
        )}
      </div>
      <div>
        <button className="btn sm" onClick={() => onOpenPlan(seedFrom(doc, f))}>
          {f.type === 'strength' ? 'Open an enrichment plan' : 'Open a support plan'}
        </button>
      </div>
    </div>
  )
}

function DocumentView({ id, onOpenPlan, onChanged }: {
  id: number; onOpenPlan: (seed: Recommendation) => void; onChanged: () => void
}) {
  const [doc, setDoc] = useState<StudentDocumentDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showText, setShowText] = useState(false)

  const load = useCallback(async () => {
    try { setDoc(await api.document(id)); setError(null) }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Could not load that document.') }
  }, [id])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    if (doc?.status !== 'processing') return
    const t = window.setInterval(() => { void load() }, 4000)
    return () => window.clearInterval(t)
  }, [doc?.status, load])
  useEffect(() => { if (doc && doc.status !== 'processing') onChanged() }, [doc?.status])  // eslint-disable-line

  if (error) return <ErrorNote error={error} onRetry={() => void load()} />
  if (!doc) return <p className="sub" style={{ margin: 0 }}>Loading…</p>

  if (doc.status === 'processing') {
    return (
      <p className="sub" style={{ margin: 0 }}>
        Reading {doc.chunks > 1 ? `${doc.chunks} parts ` : ''}on the local model — usually a couple of
        minutes. This updates itself.
      </p>
    )
  }
  if (doc.status === 'failed') return <ErrorNote error={doc.error ?? 'The read failed.'} />

  const needs = doc.findings.filter((f) => f.type === 'need')
  const strengths = doc.findings.filter((f) => f.type === 'strength')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
      {doc.notices.map((n) => (
        <div key={n} className="banner" style={{ background: 'var(--warning-wash)', border: '1px solid var(--warning)', marginBottom: 0 }}>
          <span>{n}</span>
        </div>
      ))}
      {doc.findings.length === 0 && (
        <p className="sub" style={{ margin: 0 }}>Nothing in this document was specific enough to act on.</p>
      )}
      {needs.map((f, i) => <Finding key={`n${i}`} doc={doc} f={f} onOpenPlan={onOpenPlan} />)}
      {strengths.map((f, i) => <Finding key={`s${i}`} doc={doc} f={f} onOpenPlan={onOpenPlan} />)}

      {doc.rejected.length > 0 && (
        <details>
          <summary className="sub" style={{ cursor: 'pointer' }}>
            {doc.rejected.length} claim{doc.rejected.length === 1 ? '' : 's'} withheld — why
          </summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
            {doc.rejected.map((r, i) => (
              <div key={i} className="sub">
                <b style={{ color: 'var(--ink-2)' }}>{r.area ?? 'Unnamed'}</b> — {r.reason}
                {r.quote && <> The model offered: <i>“{r.quote.slice(0, 120)}”</i></>}
              </div>
            ))}
          </div>
        </details>
      )}

      <details open={showText} onToggle={(e) => setShowText((e.target as HTMLDetailsElement).open)}>
        <summary className="sub" style={{ cursor: 'pointer' }}>Text that was read ({doc.chars.toLocaleString()} characters)</summary>
        <pre style={{
          whiteSpace: 'pre-wrap', fontSize: 11.5, fontFamily: 'var(--font-ui)', color: 'var(--ink-2)',
          background: 'var(--card-2)', padding: 10, borderRadius: 6, marginTop: 6, maxHeight: 260, overflowY: 'auto',
        }}>{doc.text}</pre>
      </details>
      <p className="sub" style={{ margin: 0 }}>
        Read by {doc.model} in {Math.round(doc.duration_ms / 1000)}s. Every finding quotes the document
        word for word, and the gradebook check was done separately from the model.
      </p>
    </div>
  )
}

export function DocumentsBlock({ sid, name, onOpenPlan }: {
  sid: string; name: string; onOpenPlan: (seed: Recommendation) => void
}) {
  const [docs, setDocs] = useState<StudentDocumentRow[]>([])
  const [kind, setKind] = useState('teacher-note')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement | null>(null)

  const load = useCallback(async () => {
    try { setDocs(await api.documents(sid)) } catch { /* shown on upload instead */ }
  }, [sid])
  useEffect(() => { void load() }, [load])

  async function upload() {
    if (!file) return
    setBusy(true); setError(null)
    try {
      const doc = await api.uploadDocument(sid, file, kind)
      setFile(null)
      if (input.current) input.current.value = ''
      setOpen(doc.id)
      await load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The upload failed.')
    } finally { setBusy(false) }
  }

  async function remove(id: number) {
    await api.deleteDocument(id)
    if (open === id) setOpen(null)
    await load()
  }

  async function reread(id: number) {
    setError(null)
    try { await api.reanalyseDocument(id); setOpen(id); await load() }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Could not start the read.') }
  }

  return (
    <div className="block">
      <h3>Documents</h3>
      <div
        className={`dropzone${over ? ' over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault(); setOver(false)
          const dropped = e.dataTransfer.files?.[0]
          if (dropped) setFile(dropped)
        }}
      >
        <div style={{ fontSize: 12.5 }}>
          Upload a teacher note, report card, assessment or piece of work about {name.split(' ')[0]} to
          find what they need help with.
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="field" style={{ flex: 1, minWidth: 180 }}>
            <label htmlFor="doc-file">File</label>
            <input id="doc-file" ref={input} className="inp" type="file" accept=".pdf,.docx,.txt,.md"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
          <div className="field" style={{ minWidth: 150 }}>
            <label htmlFor="doc-kind">What is it</label>
            <select id="doc-kind" className="inp" value={kind} onChange={(e) => setKind(e.target.value)}>
              {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <button className="btn primary" disabled={!file || busy} onClick={() => void upload()}>
            {busy ? 'Uploading…' : 'Upload and read'}
          </button>
        </div>
        <div className="sub">
          PDF, Word or text, up to 10 MB. Scans and photos can't be read — there's no vision model
          installed. Only the extracted text is kept, never the file, and it stays on this machine.
        </div>
      </div>
      {error && <ErrorNote error={error} />}

      {docs.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {docs.map((d) => (
            <div key={d.id} className="panelbox panelbox-pad" style={{ padding: '10px 12px' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <button className="rowbtn" style={{ fontSize: 13, flex: 1, minWidth: 0, textAlign: 'left' }}
                  onClick={() => setOpen(open === d.id ? null : d.id)} aria-expanded={open === d.id}>
                  {d.filename}
                </button>
                {d.status === 'processing' && <Pill kind="accent">reading…</Pill>}
                {d.status === 'failed' && <Pill kind="critical">failed</Pill>}
                {d.status === 'done' && (
                  <span className="sub nowrap">
                    {d.needs} need{d.needs === 1 ? '' : 's'} · {d.strengths} strength{d.strengths === 1 ? '' : 's'}
                    {d.withheld > 0 && <> · {d.withheld} withheld</>}
                  </span>
                )}
              </div>
              <div className="sub" style={{ marginTop: 2 }}>
                {KINDS.find(([v]) => v === d.kind)?.[1] ?? d.kind}
                {d.pages ? ` · ${d.pages} page${d.pages === 1 ? '' : 's'}` : ''}
                {d.status === 'done' && d.summary && <> · {d.summary}</>}
              </div>
              {open === d.id && (
                <div style={{ marginTop: 10 }}>
                  <DocumentView id={d.id} onOpenPlan={onOpenPlan} onChanged={() => void load()} />
                  <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
                    <button className="btn sm ghost" disabled={d.status === 'processing'} onClick={() => void reread(d.id)}>
                      Read again
                    </button>
                    <button className="btn sm ghost" onClick={() => void remove(d.id)}>Delete document</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
