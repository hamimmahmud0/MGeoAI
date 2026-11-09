import { useEffect, useMemo, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../lib/api'
import { buildPopup } from '../lib/popup'
import type { MapCollection, MapData, MapProps } from '../types'
import { SEVERITY_STEPS, VEHICLE_COLORS, YEAR_COLORS, type ColorBy } from '../lib/mapStyle'
import { MapView } from './MapView'

function PinnedCard({ props, onOpen, onClose }: { props: MapProps; onOpen: (id: string) => void; onClose: () => void }) {
  const holder = useRef<HTMLDivElement>(null)
  useEffect(() => { holder.current?.replaceChildren(buildPopup(props as never, onOpen)) }, [props, onOpen])
  return (
    <div className="panel absolute right-14 top-3 z-10 max-h-[78%] w-[min(380px,calc(100%-5rem))] overflow-auto p-3 shadow-lg" role="dialog" aria-label="Incident details">
      <button className="btn absolute right-2 top-2 !h-6 !px-1.5" onClick={onClose} aria-label="Close details"><X size={12} /></button>
      <div ref={holder} className="pr-8 text-[12px]" />
    </div>
  )
}

const num = (value: unknown) => Number(value ?? 0) || 0

export function MapTab({ theme, onOpenArticle }: { theme: 'light' | 'dark'; onOpenArticle: (id: string) => void }) {
  const [sources, setSources] = useState<string[]>([])
  const [source, setSource] = useState('')
  const [data, setData] = useState<MapCollection | null>(null)
  const [meta, setMeta] = useState<MapData['meta']>()
  const [locked, setLocked] = useState(true)
  const [selected, setSelected] = useState<string>()
  const [colorBy, setColorBy] = useState<ColorBy>('severity')
  const [year, setYear] = useState<'all' | number>('all')
  const [minKilled, setMinKilled] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    api.sources().then((res) => { setLocked(res.locked); setSources(res.sources ?? []); setSource((current) => current || (res.sources?.includes('grouped') ? 'grouped' : 'gold')) }).catch((cause: Error) => setError(cause.message))
  }, [])
  useEffect(() => {
    const load = async () => {
      if (!locked && !source) return
      try {
        if (locked) {
          const coverage = await api.coverage()
          setData({ ...coverage, features: coverage.features.map((feature): MapCollection['features'][number] => { const props = (feature.properties ?? {}) as MapProps & { country?: string }; return { ...feature, properties: { ...props, incident_id: String(props.country), location_name: `${props.country} · ${props.articles}` } } }) })
          setMeta(undefined)
        } else {
          const res = await api.incidents(source)
          if (res.locked) { setLocked(true); return }
          setMeta(res.meta)
          setData({ ...res, features: res.features.map((feature): MapCollection['features'][number] => ({ ...feature, properties: { ...feature.properties, location_name: feature.properties.location ?? '' } })) })
        }
      } catch (cause) { setError(cause instanceof Error ? cause.message : 'Failed to load map') }
    }
    void load()
  }, [locked, source])

  const years = useMemo(() => [...new Set((data?.features ?? []).map((feature) => feature.properties.year).filter((value): value is number => typeof value === 'number'))].sort(), [data])
  const shown = useMemo<MapCollection>(() => ({
    type: 'FeatureCollection',
    features: (data?.features ?? []).filter((feature) => locked || ((year === 'all' || feature.properties.year === year) && num(feature.properties.killed_n) >= minKilled)),
  }), [data, locked, year, minKilled])
  const killedTotal = shown.features.reduce((sum, feature) => sum + num(feature.properties.killed_n), 0)
  const picked = shown.features.find((feature) => feature.properties.incident_id === selected)?.properties
  const grouped = source === 'grouped'

  return (
    <div className="relative h-[calc(100vh-49px)] min-h-[480px]">
      <MapView data={shown as unknown as GeoJSON.FeatureCollection<GeoJSON.Point>} selectedId={selected} colorBy={colorBy} onSelect={setSelected} onBounds={() => undefined} onOpenArticle={onOpenArticle} theme={theme} className="absolute inset-0" />

      <div className="panel absolute left-3 top-3 z-10 flex max-w-[min(560px,calc(100%-5rem))] flex-col gap-2 p-3 shadow-lg">
        {locked ? (
          <p><span className="label block">World map · collection countries</span>Amber points are <b>collection-country centroids with article counts</b>, not incident locations. Accident locations, sizes and summaries are published once labelling ends.</p>
        ) : (<>
          <div className="flex flex-wrap items-end gap-2">
            {sources.length > 1 && <label className="flex flex-col gap-1"><span className="label">Data</span>
              <select className="control" value={source} onChange={(event) => { setSource(event.target.value); setSelected(undefined) }}>{sources.map((name) => <option key={name} value={name}>{name === 'grouped' ? 'Grouped incidents' : name === 'gold' ? 'Human gold' : `Model: ${name}`}</option>)}</select></label>}
            <label className="flex flex-col gap-1"><span className="label">Colour by</span>
              <select className="control" value={colorBy} onChange={(event) => setColorBy(event.target.value as ColorBy)}><option value="severity">people killed</option><option value="vehicle">vehicle</option><option value="year">year</option></select></label>
            <label className="flex flex-col gap-1"><span className="label">Killed at least</span>
              <select className="control" value={minKilled} onChange={(event) => setMinKilled(Number(event.target.value))}>{[0, 2, 5, 10, 20].map((value) => <option key={value} value={value}>{value === 0 ? 'any' : value}</option>)}</select></label>
            {years.length > 1 && <div className="flex flex-col gap-1"><span className="label">Year</span><div className="flex gap-1">{(['all', ...years] as const).map((value) => (
              <button key={value} aria-pressed={year === value} className={`border px-2 py-1 ${year === value ? 'border-primary bg-primary-soft text-primary' : 'border-line text-muted'}`} onClick={() => setYear(value)}>{value}</button>))}</div></div>}
          </div>
          <p className="text-muted"><b className="text-ink">{shown.features.length}</b> incidents shown · <b className="text-ink">{killedTotal.toLocaleString()}</b> killed (highest figure reported per incident){meta ? ` · ${meta.mapped} of ${meta.records} have a position` : ''}</p>
        </>)}
        {error && <p role="alert" className="text-danger">{error}</p>}
      </div>

      {!locked && (
        <div className="panel absolute bottom-8 left-3 z-10 flex max-w-[min(440px,calc(100%-1.5rem))] flex-col gap-1 p-2 text-[11px] shadow-lg" aria-label="Legend">
          <span className="text-muted">Circle size = people killed. Circles are place centroids ({grouped ? 'OpenStreetMap' : 'geocoded'}), not crash coordinates; click one to see its uncertainty radius.</span>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {colorBy === 'severity' && SEVERITY_STEPS.map(([, color, label]) => <span key={label} className="flex items-center gap-1"><i className="inline-block size-2.5 rounded-full" style={{ background: color }} />{label} killed</span>)}
            {colorBy === 'vehicle' && VEHICLE_COLORS.map(([, color, label]) => <span key={label} className="flex items-center gap-1"><i className="inline-block size-2.5 rounded-full" style={{ background: color }} />{label}</span>)}
            {colorBy === 'year' && YEAR_COLORS.map(([value, color]) => <span key={value} className="flex items-center gap-1"><i className="inline-block size-2.5 rounded-full" style={{ background: color }} />{value}</span>)}
            <span className="flex items-center gap-1"><i className="inline-block size-3 rounded-full border border-line" style={{ background: '#f97316' }} />numbered circle = several incidents (colour = total killed)</span>
          </div>
        </div>)}

      {picked && !locked && <PinnedCard props={picked} onOpen={onOpenArticle} onClose={() => setSelected(undefined)} />}
    </div>
  )
}
