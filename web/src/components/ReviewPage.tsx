import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, LogIn, LogOut, RefreshCw, ShieldCheck, XCircle } from 'lucide-react'
import { api } from '../lib/api'
import type { ReviewerSession, Submission, SubmissionStatus } from '../types'

export function ReviewPage({ onDataChanged }: { onDataChanged: () => void }) {
  const [session, setSession] = useState<ReviewerSession>()
  const [checking, setChecking] = useState(true)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [status, setStatus] = useState<SubmissionStatus>('pending')
  const [rows, setRows] = useState<Submission[]>([])
  const [notes, setNotes] = useState<Record<string, string>>({})
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
    try { await api.reviewerLogout(session.csrf_token); setSession(undefined); setRows([]) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Logout failed') }
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
  if (!session) return <div className="mx-auto max-w-md p-4 lg:p-8"><div className="panel p-6"><div className="mb-5 grid size-10 place-items-center rounded bg-primary-soft text-primary"><ShieldCheck size={21} /></div><h2 className="text-xl font-semibold">Reviewer login</h2><p className="mt-2 text-sm leading-6 text-muted">Use reviewer credentials configured by the MGeoAI administrator.</p>{error && <p role="alert" className="mt-4 border border-danger-line bg-danger-soft p-3 text-sm text-danger">{error}</p>}<form onSubmit={login} className="mt-5 space-y-4"><label className="block"><span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-muted">Username</span><input required autoComplete="username" className="control w-full" value={username} onChange={(event) => setUsername(event.target.value)} /></label><label className="block"><span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-muted">Password</span><input required type="password" autoComplete="current-password" className="control w-full" value={password} onChange={(event) => setPassword(event.target.value)} /></label><button disabled={busy === 'login'} className="inline-flex w-full items-center justify-center gap-2 rounded bg-primary px-4 py-2.5 text-sm font-semibold text-white"><LogIn size={16} />{busy === 'login' ? 'Signing in…' : 'Sign in'}</button></form></div></div>

  return <div className="p-4 lg:p-6">
    <div className="mb-5 flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-widest text-primary">Moderation workspace</p><h2 className="mt-2 text-2xl font-semibold">Incident source review</h2><p className="mt-2 text-sm text-muted">Signed in as {session.username}. Approval loads the source and reruns fusion with the configured provider.</p></div><button onClick={logout} disabled={busy === 'logout'} className="inline-flex items-center gap-2 rounded border border-line bg-surface px-3 py-2 text-sm"><LogOut size={15} />Log out</button></div>
    {error && <div role="alert" className="mb-4 flex gap-2 border border-danger-line bg-danger-soft p-3 text-sm text-danger"><AlertCircle size={17} />{error}</div>}
    <div className="mb-4 flex flex-wrap items-center gap-2"><select aria-label="Queue status" className="control" value={status} onChange={(event) => setStatus(event.target.value as SubmissionStatus)}><option value="pending">Pending</option><option value="ingest_failed">Ingest failed</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="processing">Processing</option></select><button onClick={() => void load(status)} className="inline-flex items-center gap-2 rounded border border-line bg-surface px-3 py-2 text-sm"><RefreshCw size={15} />Refresh</button><span className="text-xs text-muted">{rows.length} submission(s)</span></div>
    {!rows.length ? <div className="panel p-10 text-center text-sm text-muted">No submissions in this queue.</div> : <div className="space-y-4">{rows.map((item) => <article key={item.submission_id} className="panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><span className="badge">{item.status.replaceAll('_', ' ')}</span><span className="badge">{item.source_kind}</span></div><h3 className="mt-3 text-lg font-semibold">{item.title}</h3><p className="mt-1 text-xs text-muted">{item.publisher || 'Unknown publisher'} · submitted {new Date(item.submitted_at).toLocaleString()} by {item.submitter_name || 'anonymous'}</p></div><span className="break-all text-[11px] text-muted">{item.submission_id}</span></div>
      {item.source_uri && <a className="mt-3 inline-block break-all text-xs font-medium text-primary hover:underline" href={item.source_uri} target="_blank" rel="noreferrer">{item.source_uri}</a>}
      <div className="mt-4 max-h-80 overflow-y-auto whitespace-pre-wrap rounded border border-line bg-canvas p-4 text-sm leading-6">{item.content}</div>
      {item.ingest_error && <p className="mt-3 rounded border border-danger-line bg-danger-soft p-3 text-xs text-danger">{item.ingest_error}</p>}
      {item.status === 'pending' || item.status === 'ingest_failed' ? <div className="mt-4 border-t border-line pt-4"><label className="block"><span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-muted">Review note</span><textarea className="min-h-20 w-full rounded border border-line bg-surface p-3 text-sm" value={notes[item.submission_id] || ''} onChange={(event) => setNotes((current) => ({ ...current, [item.submission_id]: event.target.value }))} maxLength={2000} /></label><div className="mt-3 flex flex-wrap gap-2"><button disabled={busy === item.submission_id} onClick={() => void review(item, 'approve')} className="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"><CheckCircle2 size={16} />Approve and load</button><button disabled={busy === item.submission_id} onClick={() => void review(item, 'reject')} className="inline-flex items-center gap-2 rounded border border-danger-line bg-danger-soft px-4 py-2 text-sm font-semibold text-danger disabled:opacity-60"><XCircle size={16} />Reject</button>{busy === item.submission_id && <span className="self-center text-xs text-primary">Processing pipeline…</span>}</div></div> : <div className="mt-4 border-t border-line pt-3 text-xs text-muted">Reviewed by {item.reviewed_by || 'unknown'}{item.reviewed_at ? ` on ${new Date(item.reviewed_at).toLocaleString()}` : ''}{item.review_note ? ` · ${item.review_note}` : ''}</div>}
      <details className="mt-4 text-xs"><summary className="cursor-pointer font-medium text-primary">Audit history ({item.audit.length})</summary><ul className="mt-2 space-y-1 text-muted">{item.audit.map((event, index) => <li key={`${event.at}-${index}`}>{new Date(event.at).toLocaleString()} · {event.actor} · {event.action.replaceAll('_', ' ')}{event.detail ? ` · ${event.detail}` : ''}</li>)}</ul></details>
    </article>)}</div>}
  </div>
}
