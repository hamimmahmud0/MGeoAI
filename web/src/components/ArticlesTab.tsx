import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import type { AccidentRecord, ArticleListRow, ModelResult, PublicArticle } from '../types'
import { LockNotice } from './Lock'

const show = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—'
  return String(value)
}
const FIELDS: [keyof AccidentRecord, string][] = [
  ['fatalities', 'Fatalities'], ['casualities', 'Killed + injured'], ['vehicles', 'Vehicles'], ['date', 'Date'],
  ['country', 'Country'], ['location', 'Location'], ['longitude and latitude', 'Coordinates'],
]
type Column = { name: string; kind: 'gold' | 'human' | 'model'; accidents?: AccidentRecord[]; gold?: Record<string, unknown>; failed?: string }

function Comparison({ detail }: { detail: PublicArticle }) {
  const columns: Column[] = []
  if (detail.gold?.fields) columns.push({ name: 'Gold (majority)', kind: 'gold', gold: detail.gold.fields })
  for (const item of detail.annotators ?? []) columns.push({ name: item.annotator, kind: 'human', accidents: item.unusable ? [] : item.accidents })
  for (const item of detail.models ?? []) columns.push({ name: `${item.spec.model}${item.spec.with_images ? ' +img' : ''}`, kind: 'model', accidents: item.accidents, failed: item.status === 'failed' ? item.error ?? 'failed' : undefined })
  const first = (column: Column) => column.accidents?.find((item) => item.accident)
  const flag = (column: Column) => column.kind === 'gold' ? show(detail.gold?.accident) : column.failed ? 'failed' : column.accidents ? String(column.accidents.some((item) => item.accident)) : '—'
  return (
    <div className="overflow-x-auto"><table className="w-full border-collapse text-left"><thead><tr className="label"><th className="py-1 pr-3">Field</th>{columns.map((column) => <th key={column.name + column.kind} className="px-2">{column.name}<span className="badge ml-1">{column.kind}</span></th>)}</tr></thead>
      <tbody>
        <tr className="border-t border-line"><td className="py-1 pr-3">Accident reported</td>{columns.map((column) => <td key={column.name + column.kind} className="px-2">{flag(column)}</td>)}</tr>
        <tr className="border-t border-line"><td className="py-1 pr-3">Accidents</td>{columns.map((column) => <td key={column.name + column.kind} className="px-2">{column.kind === 'gold' ? show(detail.gold?.accident_count) : column.accidents ? column.accidents.filter((item) => item.accident).length : '—'}</td>)}</tr>
        {FIELDS.map(([field, label]) => (
          <tr key={field} className="border-t border-line"><td className="py-1 pr-3">{label}</td>{columns.map((column) => <td key={column.name + column.kind} className="px-2 align-top">{column.kind === 'gold' ? show((column.gold ?? {})[field === 'longitude and latitude' ? 'coordinates' : field]) : show(first(column)?.[field])}</td>)}</tr>))}
      </tbody></table>
      <p className="mt-1 text-muted">Showing the first accident of each source; open the sections below for all records, evidence quotes and image analyses. Gold shows normalised values (dates to the day, locations as word lists).</p></div>
  )
}

function ModelCard({ item }: { item: ModelResult }) {
  return (
    <details className="panel p-3"><summary className="cursor-pointer"><b>{item.spec.provider} · {item.spec.model}</b> <span className="badge">{item.spec.input_set}</span> <span className="badge">{item.status}</span>
      {item.quality && <span className="ml-2 text-muted">quotes verbatim {item.quality.verbatim}/{item.quality.quotes}</span>}</summary>
      <p className="mt-1 text-muted">tokens {item.input_tokens ?? '—'} in / {item.output_tokens ?? '—'} out · {item.latency_ms ?? '—'} ms · finish {item.finish_reason ?? '—'} · thinking {item.call_settings?.thinking ?? 'n/a'} · max output {item.call_settings?.max_output_tokens ?? '—'} · images sent {item.images_sent?.length ?? 0}{item.error ? ` · error: ${item.error}` : ''}</p>
      {item.accidents && <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words border border-line bg-canvas p-2">{JSON.stringify(item.accidents, null, 2)}</pre>}
      {item.images && item.images.length > 0 && <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-words border border-line bg-canvas p-2">{JSON.stringify(item.images, null, 2)}</pre>}
      {item.raw_text && <details className="mt-2"><summary className="cursor-pointer text-muted">Raw model response</summary><pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap break-words border border-line bg-canvas p-2">{item.raw_text}</pre></details>}
    </details>
  )
}

export function ArticleDetail({ detail }: { detail: PublicArticle }) {
  return (
    <div className="flex flex-col gap-4">
      <div><h2 className="text-base font-bold">{detail.title}</h2>
        <p className="text-muted">{detail.publisher} · {detail.published_at ?? 'date unknown'} · {detail.language ?? 'language unknown'} {detail.url && <>· <a className="text-primary underline" href={detail.url} target="_blank" rel="noreferrer noopener">original article</a></>}</p></div>
      {detail.locked ? <LockNotice what="Annotator and model output" /> : (<>
        <section className="panel p-3"><h3 className="label mb-2">Side-by-side comparison</h3><Comparison detail={detail} /></section>
        <section className="flex flex-col gap-2"><h3 className="label">Human annotations ({detail.annotators?.length ?? 0})</h3>
          {(detail.annotators ?? []).map((item) => (
            <details key={item.annotator} className="panel p-3"><summary className="cursor-pointer"><b>{item.annotator}</b>{item.unusable && <span className="badge ml-2">marked unusable</span>} <span className="text-muted">revision {item.revision}</span></summary>
              {item.notes && <p className="mt-1">Notes: {item.notes}</p>}
              <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words border border-line bg-canvas p-2">{JSON.stringify(item.accidents, null, 2)}</pre>
              {item.images.length > 0 && <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-words border border-line bg-canvas p-2">{JSON.stringify(item.images, null, 2)}</pre>}
            </details>))}
        </section>
        <section className="flex flex-col gap-2"><h3 className="label">Model outputs ({detail.models?.length ?? 0})</h3>{(detail.models ?? []).map((item) => <ModelCard key={item.config_id} item={item} />)}</section>
      </>)}
      {detail.images.length > 0 && <section><h3 className="label mb-2">Images ({detail.images.length})</h3>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3">{detail.images.map((image) => <a key={image.image_id} href={image.url} target="_blank" rel="noreferrer noopener"><img src={image.url} alt={image.alt || 'Article image'} loading="lazy" className="max-h-48 w-full border border-line object-contain" /></a>)}</div></section>}
      <section><h3 className="label mb-2">Article text (markdown)</h3><pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words border border-line bg-canvas p-3 leading-relaxed">{detail.markdown}</pre></section>
    </div>
  )
}

export function ArticlesTab({ articleId, onSelect }: { articleId: string | null; onSelect: (id: string | null) => void }) {
  const [rows, setRows] = useState<ArticleListRow[] | null>(null)
  const [locked, setLocked] = useState(true)
  const [query, setQuery] = useState('')
  const [detail, setDetail] = useState<PublicArticle | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { api.publicArticles().then((res) => { setRows(res.articles); setLocked(res.locked) }).catch((cause: Error) => setError(cause.message)) }, [])
  useEffect(() => {
    setDetail(null)
    if (articleId) api.publicArticle(articleId).then(setDetail).catch((cause: Error) => setError(cause.message))
  }, [articleId])
  const filtered = useMemo(() => (rows ?? []).filter((row) => `${row.title} ${row.publisher} ${row.language}`.toLowerCase().includes(query.toLowerCase())), [rows, query])
  return (
    <div className="grid min-h-[calc(100vh-49px)] grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)]">
      <aside className="border-b border-line lg:border-b-0 lg:border-r">
        <div className="flex flex-col gap-1 border-b border-line p-3"><input className="control" placeholder="Search title or publisher" aria-label="Search articles" value={query} onChange={(event) => setQuery(event.target.value)} />
          <span className="text-muted">{filtered.length} of {rows?.length ?? 0} articles{locked ? ' · annotations and model output locked' : ''}</span></div>
        <ul className="max-h-60 overflow-auto lg:max-h-[calc(100vh-130px)]">{filtered.map((row) => (
          <li key={row.id}><button className={`block w-full border-b border-line px-3 py-2 text-left hover:bg-primary-soft ${row.id === articleId ? 'bg-primary-soft' : ''}`} onClick={() => onSelect(row.id)}>
            <span className="line-clamp-2">{row.title || row.id}</span><span className="text-muted">{row.publisher}{!locked && row.gold_accident !== undefined ? ` · gold: ${row.gold_accident === null ? 'unresolved' : row.gold_accident ? 'accident' : 'no accident'} · ${row.models_with_result ?? 0} model(s)` : ''}</span></button></li>))}</ul>
      </aside>
      <section className="min-w-0 p-4">
        {error && <p role="alert" className="mb-2 border border-danger-line bg-danger-soft p-2 text-danger">{error}</p>}
        {!articleId ? <p className="text-muted">Choose an article to see its link, text, images, human annotations and model outputs.</p> : !detail ? <p className="text-muted">Loading…</p> : <ArticleDetail detail={detail} />}
      </section>
    </div>
  )
}
