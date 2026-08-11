import type { Incident, IncidentEvidence, Page, ProviderRun, Source, SourceDetail } from '../types'

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

export const api = {
  incidents: (query = '') => get<Page<Incident>>(`/api/incidents?${query}`),
  incident: (id: string) => get<Incident>(`/api/incidents/${encodeURIComponent(id)}`),
  geojson: (query = '') => get<GeoJSON.FeatureCollection<GeoJSON.Point>>(`/api/incidents.geojson?${query}`),
  sources: () => get<Page<Source>>('/api/sources?page_size=200'),
  source: (id: string) => get<SourceDetail>(`/api/sources/${encodeURIComponent(id)}`),
  evidence: (incidentId: string) => get<IncidentEvidence>(`/api/incidents/${encodeURIComponent(incidentId)}/evidence`),
  runs: () => get<Page<ProviderRun>>('/api/runs?page_size=200'),
}
