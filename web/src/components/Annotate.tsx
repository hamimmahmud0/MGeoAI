import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { VEHICLES, emptyAccident } from '../types'
import type { AccidentRecord, ArticleDetail, ArticleQueue, ImageLabel, Session } from '../types'

const intOrNull = (value: string): number | null => (value.trim() === '' ? null : Math.max(0, Math.floor(Number(value))))
const textOrNull = (value: string): string | null => (value.trim() === '' ? null : value.trim())

function AccidentForm({ value, onChange, onRemove, index }: { value: AccidentRecord; onChange: (next: AccidentRecord) => void; onRemove?: () => void; index: number }) {
  const set = (patch: Partial<AccidentRecord>) => onChange({ ...value, ...patch })
  const vehicles = value.vehicles ?? []
  const toggle = (name: string) => set({ vehicles: vehicles.includes(name) ? vehicles.filter((item) => item !== name) : [...vehicles, name] })
  const other = vehicles.filter((item) => item.startsWith('other:')).map((item) => item.slice(6)).join(', ')
  return (
    <fieldset className="panel flex flex-col gap-2 p-3">
      <legend className="label px-1">Accident {index + 1}</legend>
      <label className="flex items-center gap-2"><input type="checkbox" checked={value.accident} onChange={(event) => set(event.target.checked ? emptyAccident() : { accident: false, casualities: null, fatalities: null, vehicles: null, date: null, country: null, location: null, 'longitude and latitude': null })} />
        <span>This article reports a specific road accident</span></label>
      {value.accident && (<>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1"><span className="label">Fatalities</span>
            <input className="control" inputMode="numeric" value={value.fatalities ?? ''} onChange={(event) => set({ fatalities: intOrNull(event.target.value) })} /></label>
          <label className="flex flex-col gap-1"><span className="label">Killed + injured</span>
            <input className="control" inputMode="numeric" value={value.casualities ?? ''} onChange={(event) => set({ casualities: intOrNull(event.target.value) })} /></label>
        </div>
        <div><span className="label">Vehicles (fault first)</span>
          <div className="mt-1 flex flex-wrap gap-1">{VEHICLES.map((name) => (
            <button type="button" key={name} aria-pressed={vehicles.includes(name)} onClick={() => toggle(name)}
              className={`border px-1.5 py-0.5 text-[11px] ${vehicles.includes(name) ? 'border-primary bg-primary-soft text-primary' : 'border-line text-muted'}`}>{name}</button>))}
          </div>
          <input className="control mt-1 w-full" placeholder="other vehicle names, comma separated" value={other}
            onChange={(event) => set({ vehicles: [...vehicles.filter((item) => !item.startsWith('other:')), ...event.target.value.split(',').map((item) => item.trim()).filter(Boolean).map((item) => `other:${item}`)] })} /></div>
        <label className="flex flex-col gap-1"><span className="label">Date of accident (YYYY-MM-DD or with time +06:00)</span>
          <input className="control" placeholder="2025-11-04T14:15:00+06:00" value={value.date ?? ''} onChange={(event) => set({ date: textOrNull(event.target.value) })} /></label>
        <label className="flex flex-col gap-1"><span className="label">Country</span>
          <input className="control" value={value.country ?? ''} onChange={(event) => set({ country: textOrNull(event.target.value) })} /></label>
        <label className="flex flex-col gap-1"><span className="label">Location (specific → general)</span>
          <input className="control" value={value.location ?? ''} onChange={(event) => set({ location: textOrNull(event.target.value) })} /></label>
        <label className="flex flex-col gap-1"><span className="label">Coordinates "lat,lon" — only if stated in the article</span>
          <input className="control" placeholder="23.8103,90.4125" value={value['longitude and latitude'] ?? ''} onChange={(event) => set({ 'longitude and latitude': textOrNull(event.target.value) })} /></label>
      </>)}
      {onRemove && <button type="button" className="btn self-start" onClick={onRemove}>Remove accident</button>}
    </fieldset>
  )
}

function ImageForm({ image, label, onChange }: { image: { image_id: string; url: string; alt: string }; label: ImageLabel; onChange: (next: ImageLabel) => void }) {
  return (
    <div className="panel flex flex-col gap-2 p-3">
      <img src={image.url} alt={image.alt || 'Article image'} referrerPolicy="no-referrer" loading="lazy" className="max-h-56 w-full border border-line object-contain" />
      <textarea className="control" rows={2} placeholder="Describe what is visible" value={label.description} onChange={(event) => onChange({ ...label, description: event.target.value })} />
      <div className="flex gap-3">{([['Shows an accident', true], ['No accident', false], ['Unsure', null]] as const).map(([name, state]) => (
        <label key={name} className="flex items-center gap-1"><input type="radio" name={`img-${image.image_id}`} checked={label.shows_accident === state} onChange={() => onChange({ ...label, shows_accident: state })} />{name}</label>))}
      </div>
    </div>
  )
}

export function Annotate({ session }: { session: Session }) {
  const [queue, setQueue] = useState<ArticleQueue | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [article, setArticle] = useState<ArticleDetail | null>(null)
  const [accidents, setAccidents] = useState<AccidentRecord[]>([emptyAccident()])
  const [images, setImages] = useState<Record<string, ImageLabel>>({})
  const [unusable, setUnusable] = useState(false)
  const [notes, setNotes] = useState('')
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')

  const refresh = useCallback(() => api.articles().then(setQueue).catch((cause: Error) => setError(cause.message)), [])
  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    if (queue && !selected) setSelected(queue.articles.find((row) => !row.done)?.id ?? queue.articles[0]?.id ?? null)
  }, [queue, selected])
  useEffect(() => {
    if (!selected) return
    setStatus(''); setError('')
    api.article(selected).then((detail) => {
      setArticle(detail)
      const mine = detail.my_label
      setAccidents(mine?.accidents.length ? mine.accidents : [emptyAccident()])
      setUnusable(mine?.unusable ?? false)
      setNotes(mine?.notes ?? '')
      setImages(Object.fromEntries(detail.images.map((img) => [img.image_id, mine?.images.find((item) => item.image_id === img.image_id) ?? { image_id: img.image_id, description: '', shows_accident: null, vehicles_visible: [], notes: '' }])))
    }).catch((cause: Error) => setError(cause.message))
  }, [selected])

  const save = async (advance: boolean) => {
    if (!article) return
    setError(''); setStatus('Saving…')
    try {
      const records = unusable ? [{ ...emptyAccident(), accident: false, vehicles: null }] : accidents
      const touched = Object.values(images).filter((item) => item.description || item.shows_accident !== null)
      await api.saveLabel(article.id, { accidents: records, images: touched, unusable, notes }, session.csrf_token)
      setStatus('Saved')
      await refresh()
      if (advance && queue) {
        const rows = queue.articles
        const next = rows.slice(rows.findIndex((row) => row.id === article.id) + 1).find((row) => !row.done)
        if (next) setSelected(next.id)
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Save failed'); setStatus('') }
  }

  if (!queue) return <p className="p-6 text-muted">{error || 'Loading queue…'}</p>
  return (
    <div className="grid min-h-[calc(100vh-49px)] grid-cols-1 lg:grid-cols-[260px_minmax(0,1fr)_380px]">
      <aside className="border-b border-line lg:border-b-0 lg:border-r">
        <p className="label border-b border-line p-3">{queue.labeled}/{queue.total} done · {queue.annotator}</p>
        <ul className="max-h-48 overflow-auto lg:max-h-[calc(100vh-100px)]">{queue.articles.map((row, index) => (
          <li key={row.id}><button className={`block w-full border-b border-line px-3 py-2 text-left hover:bg-primary-soft ${row.id === selected ? 'bg-primary-soft' : ''}`} onClick={() => setSelected(row.id)}>
            <span className={row.done ? 'text-accent' : 'text-muted'}>{row.done ? '✓' : '·'} {String(index + 1).padStart(3, '0')}</span>{' '}
            <span className="line-clamp-2">{row.title || row.publisher || row.id}</span></button></li>))}</ul>
      </aside>
      <section className="min-w-0 border-b border-line p-4 lg:border-b-0 lg:border-r">
        {!article ? <p className="text-muted">{error || 'Select an article'}</p> : (<>
          <h2 className="text-base font-bold">{article.title}</h2>
          <p className="mb-3 text-muted">{article.publisher} · {article.published_at ?? 'date unknown'} · {article.url && <a className="text-primary underline" href={article.url} target="_blank" rel="noreferrer noopener">source</a>}</p>
          <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap break-words border border-line bg-canvas p-3 leading-relaxed">{article.markdown}</pre>
        </>)}
      </section>
      <section className="flex flex-col gap-3 p-4">
        {article && (<>
          <label className="flex items-center gap-2"><input type="checkbox" checked={unusable} onChange={(event) => setUnusable(event.target.checked)} /><span>Page is not a usable article (listing, paywall, empty)</span></label>
          {!unusable && accidents.map((record, index) => (
            <AccidentForm key={index} index={index} value={record}
              onChange={(next) => setAccidents(accidents.map((item, i) => (i === index ? next : item)))}
              onRemove={accidents.length > 1 ? () => setAccidents(accidents.filter((_, i) => i !== index)) : undefined} />))}
          {!unusable && accidents.every((item) => item.accident) && <button className="btn self-start" onClick={() => setAccidents([...accidents, emptyAccident()])}>+ Add separate accident</button>}
          {!unusable && article.images.length > 0 && <div className="flex flex-col gap-2"><span className="label">Images ({article.images.length})</span>
            {article.images.map((img) => <ImageForm key={img.image_id} image={img} label={images[img.image_id] ?? { image_id: img.image_id, description: '', shows_accident: null, vehicles_visible: [], notes: '' }} onChange={(next) => setImages({ ...images, [img.image_id]: next })} />)}</div>}
          <label className="flex flex-col gap-1"><span className="label">Notes</span><textarea className="control" rows={2} maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
          {error && <p role="alert" className="border border-danger-line bg-danger-soft p-2 text-danger">{error}</p>}
          <div className="flex items-center gap-2"><button className="btn btn-primary" onClick={() => void save(true)}>Save &amp; next</button><button className="btn" onClick={() => void save(false)}>Save</button><span className="text-muted" aria-live="polite">{status}</span></div>
        </>)}
      </section>
    </div>
  )
}
