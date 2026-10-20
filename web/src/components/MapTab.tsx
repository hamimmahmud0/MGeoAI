import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import type { MapCollection, MapData, MapProps, Overview } from '../types'
import { MapView } from './MapView'
import { LockNotice, Stat } from './Lock'

export function MapTab({ theme }: { theme: 'light' | 'dark' }) {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [sources, setSources] = useState<string[]>([])
  const [source, setSource] = useState('gold')
  const [data, setData] = useState<MapCollection | null>(null)
  const [meta, setMeta] = useState<MapData['meta']>()
  const [locked, setLocked] = useState(true)
  const [selected, setSelected] = useState<string>()
  const [error, setError] = useState('')

  useEffect(() => { api.overview().then(setOverview).catch((cause: Error) => setError(cause.message)) }, [])
  useEffect(() => {
    api.sources().then((res) => { setLocked(res.locked); setSources(res.sources ?? []) }).catch((cause: Error) => setError(cause.message))
  }, [])
  useEffect(() => {
    const load = async () => {
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

  const empty = useMemo<GeoJSON.FeatureCollection<GeoJSON.Point>>(() => ({ type: 'FeatureCollection', features: [] }), [])
  const picked = data?.features.find((feature) => feature.properties.incident_id === selected)?.properties
  return (
    <div className="grid min-h-[calc(100vh-49px)] grid-cols-1 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="relative min-h-[420px]">
        <MapView data={(data ?? empty) as GeoJSON.FeatureCollection<GeoJSON.Point>} selectedId={selected} onSelect={setSelected} onBounds={() => undefined} theme={theme} className="absolute inset-0" />
      </div>
      <aside className="flex flex-col gap-3 overflow-auto border-t border-line p-4 lg:border-l lg:border-t-0">
        {error && <p role="alert" className="border border-danger-line bg-danger-soft p-2 text-danger">{error}</p>}
        {locked ? <div className="panel p-3"><span className="label">World map · collection countries</span><p className="mt-1">Amber points are <b>collection-country centroids with article counts</b>, not incident locations. Incident locations are published once labelling ends.</p></div> : (
          <div className="panel flex flex-col gap-2 p-3">
            <label className="flex flex-col gap-1"><span className="label">Data source</span>
              <select className="control" value={source} onChange={(event) => { setSource(event.target.value); setSelected(undefined) }}>{sources.map((name) => <option key={name} value={name}>{name === 'gold' ? 'Human gold (verified)' : `Model: ${name}`}</option>)}</select></label>
            {meta && <p className="text-muted">{meta.mapped} of {meta.records} accidents have a map position. {meta.verified ? 'Human-annotated consensus.' : 'Unverified model output.'} Positions are place centroids, not crash coordinates.</p>}
          </div>)}
        {locked && <LockNotice what="Incident map and statistics" />}
        {overview && <div className="grid grid-cols-2 gap-2"><Stat label="Articles" value={overview.articles} /><Stat label="With images" value={overview.articles_with_images} hint={`${overview.images} images`} />
          <Stat label="Annotators" value={overview.labelling.annotators} /><Stat label="3+ labels" value={overview.labelling.articles_with_3plus_labels} hint={`of ${overview.articles}`} /></div>}
        {picked && !locked && (
          <div className="panel flex flex-col gap-1 p-3"><span className="label">{picked.verified ? 'Human gold' : 'Model output · unverified'}</span>
            <b>{picked.title}</b><span className="text-muted">{picked.publisher}</span>
            <span>Killed: {picked.fatalities ?? 'unknown'} · Killed+injured: {picked.casualities ?? 'unknown'}</span>
            <span>Date: {picked.date ?? 'unknown'}</span><span>Place: {picked.location ?? 'unknown'}{picked.country ? `, ${picked.country}` : ''}</span>
            <span className="text-muted">{picked.location_method} · ±{picked.uncertainty_radius_km} km · {picked.granularity}</span>
            {picked.source_url && <a className="text-primary underline" href={picked.source_url} target="_blank" rel="noreferrer noopener">Open source article</a>}
          </div>)}
        {overview && <div className="panel p-3"><span className="label">Top publishers</span><ul className="mt-1">{overview.top_publishers.map(([name, count]) => <li key={name} className="flex justify-between"><span>{name}</span><span className="text-muted">{count}</span></li>)}</ul></div>}
      </aside>
    </div>
  )
}
