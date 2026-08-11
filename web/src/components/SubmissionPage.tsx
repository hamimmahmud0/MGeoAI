import { useState } from 'react'
import { AlertCircle, CheckCircle2, Send } from 'lucide-react'
import { api } from '../lib/api'
import type { SubmissionInput } from '../types'

const emptyForm: SubmissionInput = { source_kind: 'news', title: '', publisher: '', source_uri: '', submitter_name: '', content: '' }

export function SubmissionPage() {
  const [form, setForm] = useState<SubmissionInput>(emptyForm)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [receipt, setReceipt] = useState<{ id: string; status: string }>()

  const update = (field: keyof SubmissionInput, value: string) => setForm((current) => ({ ...current, [field]: value }))

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setSubmitting(true); setError(''); setReceipt(undefined)
    try {
      const result = await api.submit(form)
      setReceipt({ id: result.submission_id, status: result.status })
      setForm(emptyForm)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  return <div className="mx-auto max-w-3xl p-4 lg:p-8">
    <div className="mb-6"><p className="text-xs font-semibold uppercase tracking-widest text-primary">Runtime source intake</p><h2 className="mt-2 text-2xl font-semibold">Submit a new incident source</h2><p className="mt-2 text-sm leading-6 text-muted">Paste the source as text. It enters a pending queue and is not loaded into incident fusion until an authenticated reviewer approves it.</p></div>

    {receipt && <div role="status" className="mb-5 flex gap-3 border border-primary/30 bg-primary-soft p-4 text-sm text-ink"><CheckCircle2 className="mt-0.5 shrink-0 text-primary" size={18} /><div><p className="font-semibold">Submission received for review</p><p className="mt-1 break-all">Reference: {receipt.id} · Status: {receipt.status}</p></div></div>}
    {error && <div role="alert" className="mb-5 flex gap-3 border border-danger-line bg-danger-soft p-4 text-sm text-danger"><AlertCircle className="mt-0.5 shrink-0" size={18} />{error}</div>}

    <form onSubmit={submit} className="panel space-y-5 p-5 sm:p-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Source category"><select className="control w-full" value={form.source_kind} onChange={(event) => update('source_kind', event.target.value)}><option value="news">News report</option><option value="social">Social post</option><option value="other">Other text source</option></select></Field>
        <Field label="Your name (optional)"><input className="control w-full" value={form.submitter_name || ''} onChange={(event) => update('submitter_name', event.target.value)} maxLength={120} /></Field>
      </div>
      <Field label="Source title"><input required minLength={3} maxLength={240} className="control w-full" value={form.title} onChange={(event) => update('title', event.target.value)} placeholder="Headline or a clear description" /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Publisher (optional)"><input className="control w-full" value={form.publisher || ''} onChange={(event) => update('publisher', event.target.value)} maxLength={160} /></Field>
        <Field label="Original URL (optional)"><input type="url" className="control w-full" value={form.source_uri || ''} onChange={(event) => update('source_uri', event.target.value)} placeholder="https://…" /></Field>
      </div>
      <Field label="Scrap content as text" help={`${form.content.length.toLocaleString()} / 100,000 characters`}><textarea aria-label="Scrap content as text" required minLength={20} maxLength={100000} className="min-h-64 w-full rounded-md border border-line bg-surface p-3 text-sm leading-6 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary" value={form.content} onChange={(event) => update('content', event.target.value)} placeholder="Paste the complete relevant source text here. Markup is treated as text and never executed." /></Field>
      <div className="rounded border border-line bg-canvas p-3 text-xs leading-5 text-muted">Do not include passwords, API keys, private contact data, or unrelated personal information. Reviewers will see the exact submitted text and metadata.</div>
      <button disabled={submitting} className="inline-flex w-full items-center justify-center gap-2 rounded bg-primary px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"><Send size={16} />{submitting ? 'Submitting…' : 'Submit for review'}</button>
    </form>
  </div>
}

function Field({ label, help, children }: { label: string; help?: string; children: React.ReactNode }) {
  return <label className="block"><span className="mb-2 flex items-center justify-between gap-3 text-xs font-semibold uppercase tracking-wide text-muted"><span>{label}</span>{help && <span className="font-normal normal-case tracking-normal">{help}</span>}</span>{children}</label>
}
