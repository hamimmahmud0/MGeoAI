import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { AnnotationArticle, AnnotationLabel, AnnotationQueue, ReviewerSession } from '../types'

const OPTIONS: { value: AnnotationLabel; label: string; hint: string }[] = [
  { value: 'same_incident', label: 'Same incident', hint: 'Both reports describe the same real-world event' },
  { value: 'related_distinct', label: 'Related, distinct', hint: 'Connected (same place, road, or cause) but different events' },
  { value: 'different', label: 'Different', hint: 'Unrelated events' },
  { value: 'cannot_tell', label: 'Cannot tell', hint: 'Not enough information to decide' },
]

export function Annotate() {
  const [session, setSession] = useState<ReviewerSession | null | undefined>(undefined)
  useEffect(() => { api.reviewerMe().then(setSession).catch(() => setSession(null)) }, [])
  if (session === undefined) return <p className="p-6 text-sm text-muted" role="status">Checking sign-in…</p>
  if (!session) return <Login onDone={setSession} />
  return <Workspace session={session} onSignOut={() => api.reviewerLogout(session.csrf_token).catch(() => undefined).finally(() => setSession(null))} />
}

function Login({ onDone }: { onDone: (session: ReviewerSession) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const submit = (event: React.FormEvent) => {
    event.preventDefault(); setError('')
    api.reviewerLogin(username.trim().toLowerCase(), password).then(onDone).catch((reason: Error) => setError(reason.message))
  }
  return <form onSubmit={submit} className="panel mx-auto mt-10 w-full max-w-sm space-y-3 p-5">
    <h2 className="text-base font-semibold">Annotator sign-in</h2>
    <p className="text-xs text-muted">Labels are submitted under your name and require your password. This is the same account as the reviewer workspace.</p>
    <label className="block text-sm">Username<input className="control mt-1 w-full" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required /></label>
    <label className="block text-sm">Password<input className="control mt-1 w-full" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    <button className="control w-full bg-ink font-medium text-canvas" type="submit">Sign in</button>
  </form>
}

function Workspace({ session, onSignOut }: { session: ReviewerSession; onSignOut: () => void }) {
  const [queue, setQueue] = useState<AnnotationQueue>()
  const [index, setIndex] = useState(0)
  const [label, setLabel] = useState<AnnotationLabel | ''>('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')

  const load = useCallback(() => api.annotationItems().then(setQueue).catch((reason: Error) => setError(reason.message)), [])
  useEffect(() => { void load() }, [load])

  const row = queue?.items[index]
  useEffect(() => { setLabel(row?.my_label?.label ?? ''); setNotes(row?.my_label?.notes ?? ''); setSaved('') }, [row])

  const save = () => {
    if (!row || !label) return
    setError('')
    api.saveAnnotation(row.item_id, label, notes, session.csrf_token)
      .then(() => { setSaved('Saved'); return load() })
      .catch((reason: Error) => setError(reason.message))
  }
  const go = (delta: number) => queue && setIndex((value) => Math.min(queue.items.length - 1, Math.max(0, value + delta)))

  return <div className="p-4 lg:p-6">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm"><span className="font-semibold">{session.username}</span>{queue && <span className="ml-3 text-muted">{queue.labeled}/{queue.total} labelled</span>}</p>
      <button className="control" onClick={onSignOut}>Sign out</button>
    </div>
    {error && <p role="alert" className="mb-3 border border-danger-line bg-danger-soft p-3 text-sm text-danger">{error}</p>}
    {queue && !queue.items.length && <p className="text-sm text-muted">No items have been imported yet.</p>}
    {row && queue && <>
      <p className="mb-2 text-xs text-muted">Pair {index + 1} of {queue.total}{row.my_label ? ` · your label: ${row.my_label.label} (revision ${row.my_label.revision})` : ' · not yet labelled'}</p>
      <div className="grid gap-4 md:grid-cols-2"><Article side="Report A" article={row.left} /><Article side="Report B" article={row.right} /></div>
      <fieldset className="mt-4 space-y-2"><legend className="text-sm font-semibold">Do these two reports describe the same real-world incident?</legend>
        {OPTIONS.map((option) => <label key={option.value} className="flex items-start gap-2 text-sm"><input type="radio" name="label" className="mt-1" checked={label === option.value} onChange={() => setLabel(option.value)} /><span><span className="font-medium">{option.label}</span><span className="ml-2 text-xs text-muted">{option.hint}</span></span></label>)}
      </fieldset>
      <label className="mt-3 block text-sm">Notes (optional)<textarea className="control mt-1 h-20 w-full py-2" maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
      <div className="mt-3 flex items-center gap-2"><button className="control bg-ink font-medium text-canvas disabled:opacity-50" disabled={!label} onClick={save}>{row.my_label ? 'Update label' : 'Submit label'}</button><button className="control" onClick={() => go(-1)} disabled={index === 0}>Previous</button><button className="control" onClick={() => go(1)} disabled={index === queue.items.length - 1}>Next</button>{saved && <span role="status" className="text-xs text-primary">{saved}</span>}</div>
    </>}
  </div>
}

function Article({ side, article }: { side: string; article: AnnotationArticle }) {
  return <article className="panel p-4"><p className="text-[11px] font-semibold uppercase tracking-wide text-muted">{side}</p>
    <h3 className="mt-1 text-sm font-semibold">{article.title}</h3>
    <p className="mt-1 text-xs text-muted">{[article.publisher, article.published_at].filter(Boolean).join(' · ')}</p>
    {article.url && <a href={article.url} target="_blank" rel="noreferrer noopener" className="text-xs text-primary underline">Open original</a>}
    <p className="mt-3 max-h-80 overflow-y-auto whitespace-pre-wrap text-sm leading-6">{article.text}</p></article>
}
