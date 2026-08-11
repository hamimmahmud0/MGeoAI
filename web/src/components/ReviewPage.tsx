import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, Download, Eye, FileText, LogIn, LogOut, RefreshCw, ShieldCheck, XCircle } from 'lucide-react'
import { api } from '../lib/api'
import type { ReviewerSession, Submission, SubmissionFile, SubmissionStatus } from '../types'

export function ReviewPage({ onDataChanged }: { onDataChanged: () => void }) {
  const [session, setSession] = useState<ReviewerSession>()
  const [checking, setChecking] = useState(true)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [status, setStatus] = useState<SubmissionStatus>('pending')
  const [rows, setRows] = useState<Submission[]>([])
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [previews, setPreviews] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async (selectedStatus: SubmissionStatus) => {
    setError('')
    try {
      const result = await api.reviewerSubmissions(selectedStatus)
      setRows(result.items)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load review queue')
    }
  }, [])

  useEffect(() => {
    api.reviewerMe().then((result) => { setSession(result); return load(status) }).catch(() => undefined).finally(() => setChecking(false))
  }, [load, status])

  async function login(event: React.FormEvent) {
    event.preventDefault(); setBusy('login'); setError('')
    try {
      const result = await api.reviewerLogin(username, password)
      setSession(result); setPassword(''); await load(status)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Login failed') }
    finally { setBusy('') }
  }

  async function logout() {
    if (!session) return
    setBusy('logout'); setError('')
    try { await api.reviewerLogout(session.csrf_token); setSession(undefined); setRows([]); setPreviews({}) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Logout failed') }
    finally { setBusy('') }
  }

  async function previewFile(item: Submission, file: SubmissionFile) {
    const key = `${item.submission_id}:${file.file_id}`
    if (previews[key] !== undefined) {
      setPreviews((current) => { const next = { ...current }; delete next[key]; return next })
      return
    }
    setBusy(key); setError('')
    try {
      const content = await api.reviewerFileText(item.submission_id, file.file_id)
      setPreviews((current) => ({ ...current, [key]: content }))
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to preview file') }
    finally { setBusy('') }
  }

  async function review(item: Submission, decision: 'approve' | 'reject') {
    if (!session) return
    setBusy(item.submission_id); setError('')
    try {
      await api.reviewSubmission(item.submission_id, decision, notes[item.submission_id] || '', session.csrf_token)
      await load(status)
      if (decision === 'approve') onDataChanged()
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Review action failed'
      await load(status); setError(message)
    }
    finally { setBusy('') }
  }

  if (checking) return <div className="p-8 text-sm text-primary" role="status">Checking reviewer session…</div>
  if (!session) return <LoginPanel username={username} password={password} busy={busy === 'login'} error={error} onUsername={setUsername} onPassword={setPassword} onSubmit={login} />

  return <div className="p-4 lg:p-6">
    <div className="mb-5 flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-widest text-primary">Moderation workspace</p><h2 className="mt-2 text-2xl font-semibold">Incident source review</h2><p className="mt-2 text-sm text-muted">Signed in as {session.username}. Inspect every quarantined file before approval loads it with the configured provider.</p></div><button onClick={logout} disabled={busy === 'logout'} className="inline-flex items-center gap-2 rounded border border-line bg-surface px-3 py-2 text-sm"><LogOut size={15} />Log out</button></div>
    {error && <div role="alert" className="mb-4 flex gap-2 border border-danger-line bg-danger-soft p-3 text-sm text-danger"><AlertCircle size={17} />{error}</div>}
    <div className="mb-4 flex flex-wrap items-center gap-2"><select aria-label="Queue status" className="control" value={status} onChange={(event) => setStatus(event.target.value as SubmissionStatus)}><option value="pending">Pending</option><option value="ingest_failed">Ingest failed</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="processing">Processing</option></select><button onClick={() => void load(status)} className="inline-flex items-center gap-2 rounded border border-line bg-surface px-3 py-2 text-sm"><RefreshCw size={15} />Refresh</button><span className="text-xs text-muted">{rows.length} submission(s)</span></div>
    {!rows.length ? <div className="panel p-10 text-center text-sm text-muted">No submissions in this queue.</div> : <div className="space-y-4">{rows.map((item) => <article key={item.submission_id} className="panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><span className="badge">{item.status.replaceAll('_', ' ')}</span><span className="badge">{submissionLabel(item)}</span></div><h3 className="mt-3 text-lg font-semibold">{item.original_filename || item.title}</h3><p className="mt-1 text-xs text-muted">Submitted {new Date(item.submitted_at).toLocaleString()} by {item.submitter_name || 'anonymous'}{item.size_bytes !== undefined ? ` · ${formatBytes(item.size_bytes)}` : ''}</p></div><span className="break-all text-[11px] text-muted">{item.submission_id}</span></div>
      {item.sha256 && <p className="mt-3 break-all font-mono text-[11px] text-muted">SHA-256 {item.sha256}</p>}
      {item.submission_type && <a className="mt-3 inline-flex items-center gap-2 rounded border border-line bg-surface px-3 py-2 text-xs font-semibold text-primary" href={api.reviewerDownloadUrl(item.submission_id)}><Download size={14} />Download original {item.submission_type === 'html_bundle' ? 'ZIP' : 'JSON'}</a>}
      {item.files?.length ? <div className="mt-4 rounded border border-line"><div className="border-b border-line bg-canvas px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted">Quarantined files ({item.files.length})</div>{item.files.map((file) => { const key = `${item.submission_id}:${file.file_id}`; return <div key={file.file_id} className="border-b border-line p-4 last:border-b-0"><div className="flex flex-wrap items-center justify-between gap-3"><div className="flex min-w-0 items-center gap-2"><FileText className="shrink-0 text-primary" size={16} /><div className="min-w-0"><p className="truncate text-sm font-semibold">{file.path}</p><p className="text-[11px] text-muted">{file.kind.replaceAll('_', ' ')} · {formatBytes(file.size_bytes)}</p></div></div><button onClick={() => void previewFile(item, file)} disabled={busy === key} className="inline-flex items-center gap-2 rounded border border-line bg-surface px-3 py-1.5 text-xs font-semibold"><Eye size={14} />{busy === key ? 'Loading…' : previews[key] !== undefined ? 'Hide text' : 'Preview text'}</button></div>{previews[key] !== undefined && <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-words rounded bg-canvas p-4 text-xs leading-5 text-ink">{previews[key]}</pre>}</div>})}</div> : item.content && <pre className="mt-4 max-h-80 overflow-y-auto whitespace-pre-wrap rounded border border-line bg-canvas p-4 text-sm leading-6">{item.content}</pre>}
      {item.ingest_error && <p className="mt-3 rounded border border-danger-line bg-danger-soft p-3 text-xs text-danger">{item.ingest_error}</p>}
      {item.status === 'pending' || item.status === 'ingest_failed' ? <div className="mt-4 border-t border-line pt-4"><label className="block"><span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-muted">Review note</span><textarea className="min-h-20 w-full rounded border border-line bg-surface p-3 text-sm" value={notes[item.submission_id] || ''} onChange={(event) => setNotes((current) => ({ ...current, [item.submission_id]: event.target.value }))} maxLength={2000} /></label><div className="mt-3 flex flex-wrap gap-2"><button disabled={busy === item.submission_id} onClick={() => void review(item, 'approve')} className="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"><CheckCircle2 size={16} />Approve and load</button><button disabled={busy === item.submission_id} onClick={() => void review(item, 'reject')} className="inline-flex items-center gap-2 rounded border border-danger-line bg-danger-soft px-4 py-2 text-sm font-semibold text-danger disabled:opacity-60"><XCircle size={16} />Reject</button>{busy === item.submission_id && <span className="self-center text-xs text-primary">Processing pipeline…</span>}</div></div> : <div className="mt-4 border-t border-line pt-3 text-xs text-muted">Reviewed by {item.reviewed_by || 'unknown'}{item.reviewed_at ? ` on ${new Date(item.reviewed_at).toLocaleString()}` : ''}{item.review_note ? ` · ${item.review_note}` : ''}</div>}
      <details className="mt-4 text-xs"><summary className="cursor-pointer font-medium text-primary">Audit history ({item.audit.length})</summary><ul className="mt-2 space-y-1 text-muted">{item.audit.map((event, index) => <li key={`${event.at}-${index}`}>{new Date(event.at).toLocaleString()} · {event.actor} · {event.action.replaceAll('_', ' ')}{event.detail ? ` · ${event.detail}` : ''}</li>)}</ul></details>
    </article>)}</div>}
  </div>
}

function LoginPanel({ username, password, busy, error, onUsername, onPassword, onSubmit }: { username: string; password: string; busy: boolean; error: string; onUsername: (value: string) => void; onPassword: (value: string) => void; onSubmit: (event: React.FormEvent) => void }) {
  return <div className="mx-auto max-w-md p-4 lg:p-8"><div className="panel p-6"><div className="mb-5 grid size-10 place-items-center rounded bg-primary-soft text-primary"><ShieldCheck size={21} /></div><h2 className="text-xl font-semibold">Reviewer login</h2><p className="mt-2 text-sm leading-6 text-muted">Use reviewer credentials configured by the MGeoAI administrator.</p>{error && <p role="alert" className="mt-4 border border-danger-line bg-danger-soft p-3 text-sm text-danger">{error}</p>}<form onSubmit={onSubmit} className="mt-5 space-y-4"><label className="block"><span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-muted">Username</span><input required autoComplete="username" className="control w-full" value={username} onChange={(event) => onUsername(event.target.value)} /></label><label className="block"><span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-muted">Password</span><input required type="password" autoComplete="current-password" className="control w-full" value={password} onChange={(event) => onPassword(event.target.value)} /></label><button disabled={busy} className="inline-flex w-full items-center justify-center gap-2 rounded bg-primary px-4 py-2.5 text-sm font-semibold text-white"><LogIn size={16} />{busy ? 'Signing in…' : 'Sign in'}</button></form></div></div>
}

function submissionLabel(item: Submission) {
  if (item.submission_type === 'html_bundle') return 'HTML bundle'
  if (item.submission_type === 'video_json') return 'video JSON'
  return 'legacy text'
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}
