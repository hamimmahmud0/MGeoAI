import { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, AlertCircle, ClipboardCheck, Database, Filter, Globe2, List, Map as MapIcon, Menu, Monitor, Moon, Search, Sun, Upload, Workflow } from 'lucide-react'
import { CoverageMap } from './components/CoverageMap'
import { IncidentDetail } from './components/IncidentDetail'
import { MapView } from './components/MapView'
import { ReviewPage } from './components/ReviewPage'
import { SourceInspector } from './components/SourceInspector'
import { SubmissionPage } from './components/SubmissionPage'
import { api } from './lib/api'
import type { CoverageCollection, Incident, ProviderRun, Source, SourceDetail } from './types'

type Screen = 'overview' | 'coverage' | 'sources' | 'submit' | 'review' | 'runs'
type MobileView = 'map' | 'list'
type Theme = 'system' | 'light' | 'dark'

function initialParams() { return new URLSearchParams(window.location.search) }
function initialTheme(): Theme {
  const stored = window.localStorage.getItem('mgeoai-theme') || window.localStorage.getItem('traffic-fusion-theme')
  return stored === 'light' || stored === 'dark' ? stored : 'system'
}
function systemTheme(): 'light' | 'dark' {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function App() {
  const params = initialParams()
  const [screen, setScreen] = useState<Screen>((params.get('screen') as Screen) || 'overview')
  const [mobileNav, setMobileNav] = useState(false)
  const [selected, setSelected] = useState(params.get('incident') || '')
  const [mobileView, setMobileView] = useState<MobileView>('map')
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [geojson, setGeojson] = useState<GeoJSON.FeatureCollection<GeoJSON.Point>>({ type: 'FeatureCollection', features: [] })
  const [coverage, setCoverage] = useState<CoverageCollection>({ type: 'FeatureCollection', features: [] })
  const [sources, setSources] = useState<Source[]>([])
  const [runs, setRuns] = useState<ProviderRun[]>([])
  const [sourceDetail, setSourceDetail] = useState<SourceDetail>()
  const [sourceLoading, setSourceLoading] = useState(false)
  const [dataVersion, setDataVersion] = useState(0)
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>(() => initialTheme() === 'system' ? systemTheme() : initialTheme() as 'light' | 'dark')
  const [bbox, setBbox] = useState('')
  const [search, setSearch] = useState(params.get('search') || '')
  const [type, setType] = useState(params.get('type') || '')
  const [severity, setSeverity] = useState(params.get('severity') || '')
  const [confidence, setConfidence] = useState(params.get('confidence') || '')
  const [sourceCount, setSourceCount] = useState(params.get('sources') || '')
  const [sentiment, setSentiment] = useState(params.get('sentiment') || '')
  const [fromDate, setFromDate] = useState(params.get('from') || '')
  const [toDate, setToDate] = useState(params.get('to') || '')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    const apply = () => {
      const resolved = theme === 'system' ? systemTheme() : theme
      document.documentElement.dataset.theme = resolved
      document.documentElement.style.colorScheme = resolved
      setResolvedTheme(resolved)
    }
    apply()
    window.localStorage.setItem('mgeoai-theme', theme)
    window.localStorage.removeItem('traffic-fusion-theme')
    media?.addEventListener('change', apply)
    return () => media?.removeEventListener('change', apply)
  }, [theme])

  const filterQuery = useMemo(() => {
    const query = new URLSearchParams()
    if (bbox) query.set('bbox', bbox)
    if (search) query.set('search', search)
    if (type) query.set('type', type)
    if (severity) query.set('severity', severity)
    if (confidence) query.set('confidence', confidence)
    if (sourceCount) query.set('source_count', sourceCount)
    if (sentiment) query.set('sentiment', sentiment)
    if (fromDate) query.set('from', fromDate)
    if (toDate) query.set('to', toDate)
    query.set('page_size', '200')
    return query.toString()
  }, [bbox, search, type, severity, confidence, sourceCount, sentiment, fromDate, toDate])

  useEffect(() => {
    const query = new URLSearchParams()
    query.set('screen', screen)
    if (selected) query.set('incident', selected)
    if (search) query.set('search', search)
    if (type) query.set('type', type)
    if (severity) query.set('severity', severity)
    if (confidence) query.set('confidence', confidence)
    if (sourceCount) query.set('sources', sourceCount)
    if (sentiment) query.set('sentiment', sentiment)
    if (fromDate) query.set('from', fromDate)
    if (toDate) query.set('to', toDate)
    window.history.replaceState(null, '', `${window.location.pathname}?${query}`)
  }, [screen, selected, search, type, severity, confidence, sourceCount, sentiment, fromDate, toDate])

  useEffect(() => {
    if (screen !== 'overview' || !bbox) return
    const controller = new AbortController()
    setLoading(true); setError('')
    Promise.all([api.incidents(filterQuery), api.geojson(filterQuery)])
      .then(([page, features]) => { setIncidents(page.items); setGeojson(features) })
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [filterQuery, bbox, screen, dataVersion])

  useEffect(() => {
    if (screen === 'coverage' && !coverage.features.length) api.coverage().then(setCoverage).catch((reason: Error) => setError(reason.message))
    if (screen === 'sources' && !sources.length) api.sources().then((data) => setSources(data.items)).catch((reason: Error) => setError(reason.message))
    if (screen === 'runs' && !runs.length) api.runs().then((data) => setRuns(data.items)).catch((reason: Error) => setError(reason.message))
  }, [screen, coverage.features.length, sources.length, runs.length, dataVersion])

  const selectIncident = useCallback((id: string) => { setSelected(id); setMobileView('map') }, [])
  const inspectSource = useCallback((id: string) => {
    setSourceLoading(true)
    setError('')
    api.source(id)
      .then(setSourceDetail)
      .catch((reason: Error) => setError(`Unable to load source content: ${reason.message}`))
      .finally(() => setSourceLoading(false))
  }, [])
  const dataChanged = useCallback(() => {
    setCoverage({ type: 'FeatureCollection', features: [] }); setSources([]); setRuns([]); setDataVersion((value) => value + 1)
  }, [])
  const selectedIncident = incidents.find((item) => item.incident_id === selected)
  const mapped = incidents.filter((item) => item.mapped).length
  const countryFallbacks = incidents.filter((item) => item.geolocation.method === 'collection_country_fallback').length
  const unmapped = incidents.length - mapped

  return <div className="flex min-h-screen bg-canvas">
    <aside className="hidden w-60 shrink-0 border-r border-line bg-surface lg:block">
      <div className="flex h-16 items-center gap-3 border-b border-line px-5"><div className="grid size-8 place-items-center rounded bg-primary text-white"><Activity size={18} /></div><div><p className="text-sm font-bold">MGeoAI</p><p className="text-[11px] text-muted">Evidence operations</p></div></div>
      <nav className="space-y-1 p-3" aria-label="Primary navigation"><Nav icon={<MapIcon size={17} />} label="Overview" active={screen === 'overview'} onClick={() => setScreen('overview')} /><Nav icon={<Globe2 size={17} />} label="Global coverage" active={screen === 'coverage'} onClick={() => setScreen('coverage')} /><Nav icon={<Database size={17} />} label="Sources" active={screen === 'sources'} onClick={() => setScreen('sources')} /><Nav icon={<Upload size={17} />} label="Submit source" active={screen === 'submit'} onClick={() => setScreen('submit')} /><Nav icon={<ClipboardCheck size={17} />} label="Review queue" active={screen === 'review'} onClick={() => setScreen('review')} /><Nav icon={<Workflow size={17} />} label="Pipeline runs" active={screen === 'runs'} onClick={() => setScreen('runs')} /></nav>
      <div className="mx-4 mt-6 border-t border-line pt-4 text-xs leading-5 text-muted">Records fuse attributed reports. They do not establish truth or fault.</div>
    </aside>
    <main className="min-w-0 flex-1">
      <header className="flex min-h-16 items-center justify-between gap-3 border-b border-line bg-surface px-4 py-2 lg:px-6"><div className="flex items-center gap-3"><button onClick={() => setMobileNav((value) => !value)} className="rounded p-1 lg:hidden" aria-label="Toggle navigation" aria-expanded={mobileNav}><Menu size={21} /></button><div><h1 className="text-base font-semibold">{screenTitle(screen)}</h1><p className="text-xs text-muted">Multimodal traffic-incident intelligence</p></div></div><div className="flex items-center gap-2"><label className="relative flex items-center"><span className="pointer-events-none absolute left-2.5 text-muted">{theme === 'system' ? <Monitor size={14} /> : theme === 'dark' ? <Moon size={14} /> : <Sun size={14} />}</span><span className="sr-only">Theme</span><select aria-label="Theme" className="control w-[104px] pl-8" value={theme} onChange={(event) => setTheme(event.target.value as Theme)}><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></label><span className="badge hidden sm:inline-flex"><span className="mr-1.5 size-1.5 rounded-full bg-amber-500" />Recorded provider data</span></div></header>
      {mobileNav && <nav className="flex gap-1 overflow-x-auto border-b border-line bg-surface p-2 lg:hidden" aria-label="Mobile navigation"><Nav icon={<MapIcon size={16} />} label="Overview" active={screen === 'overview'} onClick={() => { setScreen('overview'); setMobileNav(false) }} /><Nav icon={<Globe2 size={16} />} label="Coverage" active={screen === 'coverage'} onClick={() => { setScreen('coverage'); setMobileNav(false) }} /><Nav icon={<Database size={16} />} label="Sources" active={screen === 'sources'} onClick={() => { setScreen('sources'); setMobileNav(false) }} /><Nav icon={<Upload size={16} />} label="Submit" active={screen === 'submit'} onClick={() => { setScreen('submit'); setMobileNav(false) }} /><Nav icon={<ClipboardCheck size={16} />} label="Review" active={screen === 'review'} onClick={() => { setScreen('review'); setMobileNav(false) }} /><Nav icon={<Workflow size={16} />} label="Runs" active={screen === 'runs'} onClick={() => { setScreen('runs'); setMobileNav(false) }} /></nav>}
      {screen === 'overview' && <>
        <section className="border-b border-line bg-surface px-4 py-3 lg:px-6"><div className="flex flex-wrap items-center gap-2">
          <label className="relative min-w-56 flex-1"><Search size={15} className="absolute left-3 top-2.5 text-muted" /><span className="sr-only">Search incidents</span><input className="control w-full pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search incidents or summaries" /></label>
          <Filter size={15} className="ml-1 text-muted" aria-hidden="true" />
          <select aria-label="Incident type" className="control" value={type} onChange={(e) => setType(e.target.value)}><option value="">All incident types</option><option value="road_crash">Road crash</option></select>
          <select aria-label="Severity" className="control" value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="">All severities</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="unknown">Unknown</option></select>
          <select aria-label="Mapping confidence" className="control" value={confidence} onChange={(e) => setConfidence(e.target.value)}><option value="">Any map confidence</option><option value="0.75">≥ 75%</option><option value="0.5">≥ 50%</option></select>
          <select aria-label="Source count" className="control" value={sourceCount} onChange={(e) => setSourceCount(e.target.value)}><option value="">Any source count</option><option value="2">2+ sources</option><option value="3">3+ sources</option></select>
          <select aria-label="Sentiment" className="control" value={sentiment} onChange={(e) => setSentiment(e.target.value)}><option value="">Any sentiment</option><option value="negative">Negative evidence</option><option value="mixed">Mixed evidence</option></select>
          <input aria-label="From date" type="date" className="control" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
          <input aria-label="To date" type="date" className="control" value={toDate} onChange={(e) => setToDate(e.target.value)} />
        </div></section>
        <section className="grid grid-cols-2 border-b border-line bg-surface sm:grid-cols-5"><Metric label="Visible incidents" value={incidents.length} /><Metric label="Mapped markers" value={mapped} /><Metric label="Country fallback" value={countryFallbacks} /><Metric label="Unmapped" value={unmapped} /><Metric label="Independent reports" value={incidents.reduce((sum, item) => sum + item.independent_source_count, 0)} /></section>
        <div className="flex border-b border-line bg-surface p-2 md:hidden"><button onClick={() => setMobileView('map')} className={`flex-1 rounded py-2 text-sm font-medium ${mobileView === 'map' ? 'bg-ink text-canvas' : ''}`}><MapIcon size={15} className="mr-2 inline" />Map</button><button onClick={() => setMobileView('list')} className={`flex-1 rounded py-2 text-sm font-medium ${mobileView === 'list' ? 'bg-ink text-canvas' : ''}`}><List size={15} className="mr-2 inline" />List</button></div>
        {error && <div role="alert" className="m-4 flex items-center gap-2 border border-danger-line bg-danger-soft p-3 text-sm text-danger"><AlertCircle size={17} />{error}</div>}
        <section className="grid h-[calc(100vh-244px)] min-h-[480px] grid-cols-1 md:grid-cols-[minmax(0,1fr)_390px]">
          <div className={`${mobileView === 'list' ? 'hidden' : 'block'} relative min-h-[420px] md:block`}><MapView data={geojson} selectedId={selected} onSelect={selectIncident} onBounds={setBbox} theme={resolvedTheme} /><div className="absolute bottom-6 left-3 z-10 border border-line bg-surface px-3 py-2 text-[11px] shadow-sm"><span className="mr-2 inline-block size-2 rounded-full bg-red-500" />Source-named representative <span className="ml-3 mr-2 inline-block size-2 rounded-full bg-amber-500" />Country fallback—not crash location <span className="ml-3 mr-2 inline-block size-2 rounded-full bg-primary" />Cluster <span className="ml-3 mr-2 inline-block size-2 border border-primary bg-primary-soft" />Location uncertainty</div></div>
          <div className={`${mobileView === 'map' ? 'hidden' : 'block'} overflow-y-auto border-l border-line bg-surface md:block`}><div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-surface px-4 py-3"><p className="text-xs font-semibold uppercase tracking-wider text-muted">Synchronized incident list</p>{loading && <span className="text-xs text-primary">Updating…</span>}</div>{!loading && !incidents.length ? <Empty /> : incidents.map((incident) => <IncidentRow key={incident.incident_id} incident={incident} active={selected === incident.incident_id} onSelect={selectIncident} />)}</div>
        </section>
      </>}
      {screen === 'coverage' && <CoverageView data={coverage} error={error} theme={resolvedTheme} />}
      {screen === 'sources' && <SourcesTable rows={sources} error={error} onInspect={inspectSource} />}
      {screen === 'submit' && <SubmissionPage />}
      {screen === 'review' && <ReviewPage onDataChanged={dataChanged} />}
      {screen === 'runs' && <RunsTable rows={runs} error={error} />}
    </main>
    {selectedIncident && <IncidentDetail incident={selectedIncident} onClose={() => setSelected('')} onInspectSource={inspectSource} />}
    {sourceLoading && <div className="fixed bottom-4 right-4 z-[60] rounded border border-line bg-surface px-4 py-3 text-sm shadow-lg" role="status">Loading source content…</div>}
    {sourceDetail && <SourceInspector source={sourceDetail} onClose={() => setSourceDetail(undefined)} />}
  </div>
}

function screenTitle(screen: Screen) { return { overview: 'Operational overview', coverage: 'Global source coverage', sources: 'Source registry', submit: 'Submit incident source', review: 'Reviewer workspace', runs: 'Pipeline runs' }[screen] }
function Nav({ icon, label, active, onClick }: { icon: React.ReactNode; label: string; active: boolean; onClick: () => void }) { return <button onClick={onClick} className={`flex w-full shrink-0 items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium ${active ? 'bg-primary-soft text-primary' : 'text-muted hover:bg-canvas hover:text-ink'}`}>{icon}{label}</button> }
function Metric({ label, value }: { label: string; value: number }) { return <div className="border-r border-line px-4 py-3 last:border-r-0 lg:px-6"><p className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</p><p className="mt-1 text-xl font-semibold tabular-nums">{value}</p></div> }
function IncidentRow({ incident, active, onSelect }: { incident: Incident; active: boolean; onSelect: (id: string) => void }) { return <button onClick={() => onSelect(incident.incident_id)} className={`w-full border-b border-line px-4 py-4 text-left hover:bg-canvas ${active ? 'border-l-2 border-l-primary bg-primary-soft' : ''}`}><div className="mb-2 flex items-center gap-2"><span className="badge">{incident.severity}</span><span className="text-xs text-muted">{incident.event_time.start ? new Date(incident.event_time.start).toLocaleDateString() : 'Date unknown'}</span></div><p className="text-sm font-semibold leading-5">{incident.title}</p><p className="mt-2 flex items-center gap-1 text-xs text-muted"><MapIcon size={13} />{incident.geolocation.display_name || 'Unmapped'} · {incident.geolocation.granularity}</p><p className="mt-2 text-xs text-muted">{incident.independent_source_count} independent source group(s)</p></button> }
function Empty() { return <div className="grid h-64 place-items-center p-8 text-center"><div><MapIcon className="mx-auto mb-3 text-muted" /><p className="text-sm font-medium">No incidents in this view</p><p className="mt-1 text-xs text-muted">Pan the map or broaden the active filters.</p></div></div> }
function CoverageView({ data, error, theme }: { data: CoverageCollection; error: string; theme: 'light' | 'dark' }) {
  const sources = data.features.reduce((sum, item) => sum + Number(item.properties.accepted_sources || 0), 0)
  const shared = data.features.reduce((sum, item) => sum + Number(item.properties.reviewed_multi_source_incidents || 0), 0)
  return <div>
    <section className="border-b border-line bg-surface px-4 py-4 lg:px-6"><p className="max-w-4xl text-sm leading-6 text-muted">This view shows countries represented by collected publisher sources. Markers are conservative country centroids for coverage visualization only; they are not reported crash locations.</p></section>
    <section className="grid grid-cols-3 border-b border-line bg-surface"><Metric label="Countries" value={data.features.length} /><Metric label="Accepted sources" value={sources} /><Metric label="Multi-source groups" value={shared} /></section>
    {error && <div role="alert" className="m-4 flex items-center gap-2 border border-danger-line bg-danger-soft p-3 text-sm text-danger"><AlertCircle size={17} />{error}</div>}
    <section className="grid min-h-[calc(100vh-216px)] grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="relative min-h-[480px]"><CoverageMap data={data} theme={theme} /><div className="absolute bottom-6 left-3 z-10 border border-line bg-surface px-3 py-2 text-[11px] shadow-sm"><span className="mr-2 inline-block size-2 rounded-full bg-primary" />Collection-country coverage centroid — not an incident location</div></div>
      <div className="max-h-[calc(100vh-216px)] overflow-y-auto border-l border-line bg-surface">{data.features.map((feature) => <div key={feature.properties.iso3} className="border-b border-line px-4 py-3"><div className="flex items-center justify-between gap-3"><p className="text-sm font-semibold">{feature.properties.country_name}</p><span className="badge">{feature.properties.iso3}</span></div><p className="mt-1 text-xs text-muted">{feature.properties.accepted_sources} sources · {feature.properties.reviewed_multi_source_incidents} multi-source incident(s)</p></div>)}</div>
    </section>
  </div>
}
function SourcesTable({ rows, error, onInspect }: { rows: Source[]; error: string; onInspect: (id: string) => void }) { return <TableShell error={error} empty={!rows.length} headers={['Publisher / title', 'Country', 'Platform', 'Modality', 'Dependency', 'Linked incidents', 'Content']} rows={rows.map((row) => [<div key="p"><p className="font-medium">{row.publisher || 'Unknown publisher'}</p><p className="mt-1 max-w-lg truncate text-xs text-muted">{row.title || row.local_path}</p></div>, row.country ? `${row.country} (${row.country_code || '—'})` : row.country_code || 'Unassigned', row.platform || 'local', row.source_type, row.dependency_group || row.independence, row.linked_incident_ids?.length ? String(row.linked_incident_ids.length) : 'Unlinked', <button key="inspect" onClick={() => onInspect(row.source_id)} className="rounded border border-line bg-surface px-3 py-1.5 text-xs font-medium text-primary hover:bg-canvas">Inspect content</button>])} /> }
function RunsTable({ rows, error }: { rows: ProviderRun[]; error: string }) { return <TableShell error={error} empty={!rows.length} headers={['Provider / model', 'Operation', 'Status', 'Latency', 'Usage', 'Validation']} rows={rows.map((row) => [<div key="p"><p className="font-medium">{row.provider}</p><p className="text-xs text-muted">{row.model}</p></div>, row.operation, row.finish_status, `${row.latency_ms} ms`, `${row.input_tokens ?? 0} in / ${row.output_tokens ?? 0} out`, row.validation_status])} /> }
function TableShell({ headers, rows, error, empty }: { headers: string[]; rows: React.ReactNode[][]; error: string; empty: boolean }) { return <div className="p-4 lg:p-6">{error && <p role="alert" className="mb-4 border border-danger-line bg-danger-soft p-3 text-sm text-danger">{error}</p>}<div className="panel overflow-x-auto"><table className="w-full min-w-[800px] text-left text-sm"><thead className="border-b border-line bg-canvas text-[11px] uppercase tracking-wide text-muted"><tr>{headers.map((item) => <th key={item} className="px-4 py-3 font-semibold">{item}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index} className="border-b border-line last:border-0">{row.map((cell, cellIndex) => <td key={cellIndex} className="px-4 py-3">{cell}</td>)}</tr>)}</tbody></table>{empty && <p className="p-8 text-center text-sm text-muted">No records are available.</p>}</div></div> }
