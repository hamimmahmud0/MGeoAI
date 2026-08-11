import type { Incident, IncidentEvidence, Page, ProviderRun, ReviewerSession, Source, SourceDetail, Submission, SubmissionInput, SubmissionStatus } from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...init })
  if (!response.ok) {
    const body = await response.json().catch(() => undefined) as { detail?: string } | undefined
    throw new Error(body?.detail || `${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

function jsonRequest(method: string, value?: unknown, csrfToken?: string): RequestInit {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken
  return { method, headers, body: value === undefined ? undefined : JSON.stringify(value) }
}

export const api = {
  incidents: (query = '') => request<Page<Incident>>(`/api/incidents?${query}`),
  incident: (id: string) => request<Incident>(`/api/incidents/${encodeURIComponent(id)}`),
  geojson: (query = '') => request<GeoJSON.FeatureCollection<GeoJSON.Point>>(`/api/incidents.geojson?${query}`),
  sources: () => request<Page<Source>>('/api/sources?page_size=200'),
  source: (id: string) => request<SourceDetail>(`/api/sources/${encodeURIComponent(id)}`),
  evidence: (incidentId: string) => request<IncidentEvidence>(`/api/incidents/${encodeURIComponent(incidentId)}/evidence`),
  runs: () => request<Page<ProviderRun>>('/api/runs?page_size=200'),
  submit: (value: SubmissionInput) => request<{ submission_id: string; status: SubmissionStatus; submitted_at: string }>('/api/submissions', jsonRequest('POST', value)),
  reviewerMe: () => request<ReviewerSession>('/api/reviewer/me'),
  reviewerLogin: (username: string, password: string) => request<ReviewerSession>('/api/reviewer/login', jsonRequest('POST', { username, password })),
  reviewerLogout: (csrfToken: string) => request<{ status: string }>('/api/reviewer/logout', jsonRequest('POST', undefined, csrfToken)),
  reviewerSubmissions: (status?: SubmissionStatus) => request<{ items: Submission[]; total: number }>(`/api/reviewer/submissions${status ? `?status=${status}` : ''}`),
  reviewSubmission: (id: string, decision: 'approve' | 'reject', note: string, csrfToken: string) => request<Submission>(`/api/reviewer/submissions/${encodeURIComponent(id)}/review`, jsonRequest('POST', { decision, note: note || undefined }, csrfToken)),
}
