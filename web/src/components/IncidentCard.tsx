import { useEffect, useMemo, useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../lib/api'
import type { AccidentRecord, MapProps, PublicArticle } from '../types'

type Source = { id: string; title: string | null; publisher: string | null; url: string | null; published_at: string | null }
const list = <T,>(value: unknown): T[] => (typeof value === 'string' ? (JSON.parse(value) as T[]) : (value as T[] | undefined) ?? [])
const show = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—'
  return String(value)
}
const COLUMNS: [keyof AccidentRecord, string][] = [
  ['fatalities', 'Killed'], ['casualities', 'Killed + injured'], ['vehicles', 'Vehicles'], ['date', 'Date'],
  ['country', 'Country'], ['location', 'Location'], ['longitude and latitude', 'Coordinates'],
]
const modelName = (m: NonNullable<PublicArticle['models']>[number]) =>
  `${m.spec.model}${m.spec.with_images ? ' +img' : ''}${m.spec.with_meta ? ' +date' : ''}`

type Cell = { text: string; note?: string }
type Row = { key: string; source: Source | null; cells: Record<string, Cell>; state?: string }

/** Pull the chosen source ("a:<annotator>" or "m:<run>") out of one article's detail. */
function pick(detail: PublicArticle | undefined, choice: string): { record?: AccidentRecord; state?: string } {
  if (!detail) return { state: 'loading' }
  if (detail.locked) return { state: 'hidden while labelling is open' }
  if (choice.startsWith('a:')) {
    const item = detail.annotators?.find((a) => a.annotator === choice.slice(2))
    if (!item) return { state: 'not annotated' }
    if (item.unusable) return { state: 'marked unusable' }
    const record = item.accidents.find((a) => a.accident)
    return record ? { record } : { state: 'no accident' }
  }
  const item = detail.models?.find((m) => m.config_id === choice.slice(2))
  if (!item) return { state: 'no result' }
  if (item.status === 'failed') return { state: `failed${item.error ? `: ${item.error}` : ''}` }
  const record = item.accidents?.find((a) => a.accident)
  return record ? { record } : { state: 'no accident' }
}

export function IncidentCard({ props, onOpen, onClose }: { props: MapProps; onOpen: (id: string) => void; onClose: () => void }) {
  const sources = useMemo(() => list<Source>(props.articles), [props.articles])
  const disagreements = list<string>(props.disagreements)
  const vehicles = list<string>(props.vehicles)
  const [details, setDetails] = useState<Record<string, PublicArticle>>({})
  const [failed, setFailed] = useState(false)
  const [choice, setChoice] = useState('')

  useEffect(() => {
    let alive = true
    setDetails({}); setFailed(false); setChoice('')
    Promise.all(sources.map((s) => api.publicArticle(s.id)))
      .then((all) => { if (alive) setDetails(Object.fromEntries(all.map((d) => [d.id, d]))) })
      .catch(() => { if (alive) setFailed(true) })
    return () => { alive = false }
  }, [sources])

  const loaded = Object.values(details)
  const locked = loaded.length > 0 && loaded.every((d) => d.locked)
  const options = useMemo(() => {
    const out: { value: string; label: string }[] = []
    const seen = new Set<string>()
    for (const d of loaded) for (const a of d.annotators ?? []) if (!seen.has(`a:${a.annotator}`)) { seen.add(`a:${a.annotator}`); out.push({ value: `a:${a.annotator}`, label: `Annotation · ${a.annotator}` }) }
    for (const d of loaded) for (const m of d.models ?? []) if (!seen.has(`m:${m.config_id}`)) { seen.add(`m:${m.config_id}`); out.push({ value: `m:${m.config_id}`, label: `Model output · ${modelName(m)}` }) }
    return out.sort((x, y) => x.value.localeCompare(y.value))
  }, [loaded])
  const active = options.some((o) => o.value === choice) ? choice : options[0]?.value ?? ''

  const rows: Row[] = sources.map((source) => {
    const { record, state } = pick(details[source.id], active)
    const cells: Record<string, Cell> = {}
    for (const [field] of COLUMNS) cells[field] = { text: record ? show(record[field]) : '—' }
    return { key: source.id, source, cells, state }
  })
  const fused: Row = {
    key: 'fused', source: null, state: undefined,
    cells: {
      fatalities: { text: show(props.killed) },
      casualities: { text: props.killed != null && props.injured != null ? String(props.killed + props.injured) : '—' },
      vehicles: { text: show(vehicles) }, date: { text: show(props.when) }, country: { text: '—' },
      location: { text: show(props.place) }, 'longitude and latitude': { text: '—' },
    },
  }
  // In a column with more than one distinct value, everything except the single most common value is highlighted.
  const odd = (field: string, text: string) => {
    const values = rows.filter((r) => !r.state).map((r) => r.cells[field].text).filter((t) => t !== '—')
    if (text === '—' || new Set(values).size < 2) return false
    const counts = new Map<string, number>()
    for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1)
    const top = Math.max(...counts.values())
    const leaders = [...counts.values()].filter((c) => c === top).length
    return !(counts.get(text) === top && leaders === 1)
  }

  const section = 'flex flex-col gap-2 border-t border-line pt-3 first:border-t-0 first:pt-0'
  return (
    <div className="panel absolute right-14 top-3 z-10 max-h-[84%] w-[min(760px,calc(100%-5rem))] overflow-auto p-4 shadow-lg" role="dialog" aria-label="Incident details">
      <button className="btn absolute right-2 top-2 !h-6 !px-1.5" onClick={onClose} aria-label="Close details"><X size={12} /></button>
      <div className="flex flex-col gap-3 pr-8 text-[12px]">
        <section className={section} aria-label="Summary">
          <h3 className="label">Summary</h3>
          <b className="text-[13px]">{props.headline ?? 'Incident'}</b>
          <span className="badge self-start">{props.n_articles ?? sources.length} source article(s) grouped by an LLM · fused by {props.fused_by ?? 'DeepSeek'} · unverified</span>
          <p>{props.summary}</p>
          <p>Killed: <b>{props.killed ?? 'unknown'}</b> · Injured: <b>{props.injured ?? 'unknown'}</b>{vehicles.length ? ` · ${vehicles.join(', ')}` : ''}</p>
          <p>When: {props.when ?? 'unknown'} · Place: {props.place ?? 'unknown'}</p>
          <p className="text-muted">{props.location_method} · radius {props.uncertainty_radius_km ?? '?'} km</p>
          {disagreements.length > 0 && <div className="text-muted"><p>Sources disagree on:</p><ul className="list-disc pl-4">{disagreements.slice(0, 5).map((text) => <li key={text}>{text}</li>)}</ul></div>}
        </section>

        <section className={section} aria-label="Extracted fields">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <h3 className="label">Extracted fields</h3>
            {options.length > 0 && <label className="flex items-center gap-2"><span className="label">Show</span>
              <select className="control" value={active} onChange={(event) => setChoice(event.target.value)} aria-label="Source of extracted fields">
                {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label>}
          </div>
          {failed && <p role="alert" className="text-danger">Could not load the article details.</p>}
          {locked && <p className="text-muted">Annotations and model output are hidden while labelling is open.</p>}
          {!locked && !failed && (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left">
                <thead><tr className="label">
                  <th className="py-1 pr-3">Article</th>{COLUMNS.map(([f, label]) => <th key={f} className="px-2">{label}</th>)}</tr></thead>
                <tbody>
                  <tr className="border-t border-line bg-primary-soft"><td className="py-1 pr-3 font-bold">Fused summary</td>
                    {COLUMNS.map(([f]) => <td key={f} className="px-2 align-top">{fused.cells[f].text}</td>)}</tr>
                  {rows.map((row) => (
                    <tr key={row.key} className="border-t border-line">
                      <td className="py-1 pr-3 align-top"><button className="text-left text-primary underline" onClick={() => onOpen(row.key)}>{row.source?.publisher ?? row.key}</button></td>
                      {row.state
                        ? <td colSpan={COLUMNS.length} className="px-2 text-muted">{row.state}</td>
                        : COLUMNS.map(([f]) => <td key={f} className={`px-2 align-top ${odd(f, row.cells[f].text) ? 'bg-warning-soft font-bold' : ''}`}>{row.cells[f].text}</td>)}
                    </tr>))}
                </tbody>
              </table>
              <p className="mt-1 text-muted">First accident reported for each article. Highlighted cells differ from the most common value in that column. Switch between annotations and model runs above; open an article for evidence quotes and all records.</p>
            </div>)}
        </section>

        <section className={section} aria-label="Sources">
          <h3 className="label">Sources ({sources.length})</h3>
          <ul className="flex flex-col gap-1">
            {sources.map((s) => (
              <li key={s.id} className="flex flex-wrap items-baseline gap-x-2">
                <button className="text-left text-primary underline" onClick={() => onOpen(s.id)}>{s.title ?? s.id}</button>
                <span className="text-muted">{s.publisher}{s.published_at ? ` · ${s.published_at.slice(0, 10)}` : ''}</span>
                {s.url && <a className="text-muted underline" href={s.url} target="_blank" rel="noreferrer noopener">original</a>}
              </li>))}
          </ul>
        </section>
      </div>
    </div>
  )
}
