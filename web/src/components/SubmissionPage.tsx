import { useState } from 'react'
import { AlertCircle, CheckCircle2, FileArchive, FileJson, Send, UploadCloud } from 'lucide-react'
import { api } from '../lib/api'
import type { SubmissionType } from '../types'

const maxUploadBytes = 25 * 1024 * 1024

export function SubmissionPage() {
  const [submissionType, setSubmissionType] = useState<SubmissionType>('html_bundle')
  const [submitterName, setSubmitterName] = useState('')
  const [selectedFile, setSelectedFile] = useState<File>()
  const [inputKey, setInputKey] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [receipt, setReceipt] = useState<{ id: string; status: string }>()

  function chooseType(value: SubmissionType) {
    setSubmissionType(value); setSelectedFile(undefined); setError(''); setInputKey((key) => key + 1)
  }

  function chooseFile(file?: File) {
    setError('')
    if (file && file.size > maxUploadBytes) {
      setSelectedFile(undefined); setError('The selected file exceeds the 25 MB upload limit.'); return
    }
    setSelectedFile(file)
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError(''); setReceipt(undefined)
    if (!selectedFile) { setError('Select a source package to continue.'); return }
    setSubmitting(true)
    try {
      const result = await api.submit({ submission_type: submissionType, package: selectedFile, submitter_name: submitterName || undefined })
      setReceipt({ id: result.submission_id, status: result.status })
      setSelectedFile(undefined); setSubmitterName(''); setInputKey((key) => key + 1)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  const htmlSelected = submissionType === 'html_bundle'
  return <div className="mx-auto max-w-3xl p-4 lg:p-8">
    <div className="mb-6"><p className="text-xs font-semibold uppercase tracking-widest text-primary">Runtime source intake</p><h2 className="mt-2 text-2xl font-semibold">Submit a new incident source</h2><p className="mt-2 text-sm leading-6 text-muted">Upload a source in the same structure as the supplied scraps. It remains quarantined until an authenticated reviewer inspects and approves it.</p></div>

    {receipt && <div role="status" className="mb-5 flex gap-3 border border-primary/30 bg-primary-soft p-4 text-sm text-ink"><CheckCircle2 className="mt-0.5 shrink-0 text-primary" size={18} /><div><p className="font-semibold">Submission received for review</p><p className="mt-1 break-all">Reference: {receipt.id} · Status: {receipt.status}</p></div></div>}
    {error && <div role="alert" className="mb-5 flex gap-3 border border-danger-line bg-danger-soft p-4 text-sm text-danger"><AlertCircle className="mt-0.5 shrink-0" size={18} />{error}</div>}

    <form onSubmit={submit} className="panel space-y-5 p-5 sm:p-6">
      <fieldset><legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">Input type</legend><div className="grid gap-3 sm:grid-cols-2">
        <TypeOption checked={htmlSelected} icon={<FileArchive size={20} />} title="HTML scrap bundle" detail="ZIP with one HTML page and optional analysis files" onChange={() => chooseType('html_bundle')} />
        <TypeOption checked={!htmlSelected} icon={<FileJson size={20} />} title="Video analysis JSON" detail="One video.json in the supplied analysis contract" onChange={() => chooseType('video_json')} />
      </div></fieldset>

      <div className="rounded border border-line bg-canvas p-4 text-sm leading-6"><p className="font-semibold">{htmlSelected ? 'HTML ZIP requirements' : 'Video JSON requirements'}</p>{htmlSelected ? <ul className="mt-2 list-disc space-y-1 pl-5 text-muted"><li>Exactly one UTF-8 <code>.html</code> page.</li><li>Optional <code>SOURCE_INFO.md</code> and <code>image_01.json</code> in the same folder.</li><li>Image information must be supplied as <code>image_01.json</code>; do not include raw image files.</li><li>A single enclosing folder inside the ZIP is accepted.</li></ul> : <ul className="mt-2 list-disc space-y-1 pl-5 text-muted"><li>One UTF-8 JSON object matching the video analysis files under <code>scraps/youtube</code>.</li><li>Upload the analysis JSON, not a raw video file.</li></ul>}<p className="mt-2 text-xs text-muted">Maximum upload and extracted size: 25 MB. Reviewers preview HTML and JSON as inert text.</p></div>

      <label className="block"><span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-muted">{htmlSelected ? 'HTML scrap ZIP' : 'Video analysis JSON'}</span><span className="flex cursor-pointer flex-col items-center justify-center rounded border border-dashed border-line bg-canvas px-5 py-8 text-center hover:border-primary"><UploadCloud className="mb-3 text-primary" size={28} /><span className="text-sm font-semibold">Choose {htmlSelected ? 'a .zip bundle' : 'a .json file'}</span><span className="mt-1 text-xs text-muted">Up to 25 MB</span><input key={inputKey} aria-label={htmlSelected ? 'HTML scrap ZIP' : 'Video analysis JSON'} required type="file" className="sr-only" accept={htmlSelected ? '.zip,application/zip' : '.json,application/json'} onChange={(event) => chooseFile(event.target.files?.[0])} /></span></label>
      {selectedFile && <div className="flex items-center justify-between gap-3 rounded border border-line bg-surface p-3 text-sm"><span className="min-w-0 truncate font-medium">{selectedFile.name}</span><span className="shrink-0 text-xs text-muted">{formatBytes(selectedFile.size)}</span></div>}
      <label className="block"><span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-muted">Your name (optional)</span><input className="control w-full" value={submitterName} onChange={(event) => setSubmitterName(event.target.value)} maxLength={120} /></label>
      <div className="rounded border border-line bg-canvas p-3 text-xs leading-5 text-muted">Do not include passwords, API keys, private contact data, or unrelated personal information. Reviewers can inspect every submitted file and download the original package before approval.</div>
      <button disabled={submitting} className="inline-flex w-full items-center justify-center gap-2 rounded bg-primary px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"><Send size={16} />{submitting ? 'Uploading…' : 'Submit for review'}</button>
    </form>
  </div>
}

function TypeOption({ checked, icon, title, detail, onChange }: { checked: boolean; icon: React.ReactNode; title: string; detail: string; onChange: () => void }) {
  return <label className={`flex cursor-pointer gap-3 rounded border p-4 ${checked ? 'border-primary bg-primary-soft' : 'border-line bg-surface'}`}><input type="radio" name="submission-type" className="sr-only" checked={checked} onChange={onChange} /><span className="mt-0.5 text-primary">{icon}</span><span><span className="block text-sm font-semibold">{title}</span><span className="mt-1 block text-xs leading-5 text-muted">{detail}</span></span></label>
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}
