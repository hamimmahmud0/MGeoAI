import type { CoverageCollection, Incident, IncidentEvidence, Page, ProviderRun, ReviewerSession, Source, SourceDetail, Submission, SubmissionInput, SubmissionStatus } from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...init })
  if (!response.ok) {
    const body = await response.json().catch(() => undefined) as { detail?: string } | undefined
    throw new Error(body?.detail || `${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

async function requestText(path: string): Promise<string> {
  const response = await fetch(path, { credentials: 'same-origin' })
  if (!response.ok) {
    const body = await response.json().catch(() => undefined) as { detail?: string } | undefined
    throw new Error(body?.detail || `${response.status} ${response.statusText}`)
  }
  return response.text()
}

function jsonRequest(method: string, value?: unknown, csrfToken?: string): RequestInit {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken
  return { method, headers, body: value === undefined ? undefined : JSON.stringify(value) }
}

function submissionRequest(value: SubmissionInput): RequestInit {
  const form = new FormData()
  form.set('submission_type', value.submission_type)
  form.set('package', value.package)
  if (value.submitter_name) form.set('submitter_name', value.submitter_name)
  return { method: 'POST', body: form }
}

export const api = {
  incidents: (query = '') => request<Page<Incident>>(`/api/incidents?${query}`),
  incident: (id: string) => request<Incident>(`/api/incidents/${encodeURIComponent(id)}`),
  geojson: (query = '') => request<GeoJSON.FeatureCollection<GeoJSON.Point>>(`/api/incidents.geojson?${query}`),
  coverage: () => request<CoverageCollection>('/api/coverage.geojson'),
  sources: () => request<Page<Source>>('/api/sources?page_size=1000'),
  source: (id: string) => request<SourceDetail>(`/api/sources/${encodeURIComponent(id)}`),
  evidence: (incidentId: string) => request<IncidentEvidence>(`/api/incidents/${encodeURIComponent(incidentId)}/evidence`),
  runs: () => request<Page<ProviderRun>>('/api/runs?page_size=200'),
  submit: (value: SubmissionInput) => request<{ submission_id: string; status: SubmissionStatus; submitted_at: string }>('/api/submissions', submissionRequest(value)),
  submissionStatus: (id: string) => request<{ submission_id: string; status: SubmissionStatus; submitted_at: string; reviewed_at?: string }>(`/api/submissions/${encodeURIComponent(id)}/status`),
  reviewerMe: () => request<ReviewerSession>('/api/reviewer/me'),
  reviewerLogin: (username: string, password: string) => request<ReviewerSession>('/api/reviewer/login', jsonRequest('POST', { username, password })),
  reviewerLogout: (csrfToken: string) => request<{ status: string }>('/api/reviewer/logout', jsonRequest('POST', undefined, csrfToken)),
  reviewerSubmissions: (status?: SubmissionStatus) => request<{ items: Submission[]; total: number }>(`/api/reviewer/submissions${status ? `?status=${status}` : ''}`),
  reviewerFileText: (submissionId: string, fileId: string) => requestText(`/api/reviewer/submissions/${encodeURIComponent(submissionId)}/files/${encodeURIComponent(fileId)}`),
  reviewerDownloadUrl: (submissionId: string) => `/api/reviewer/submissions/${encodeURIComponent(submissionId)}/download`,
  reviewSubmission: (id: string, decision: 'approve' | 'reject', note: string, csrfToken: string) => request<Submission>(`/api/reviewer/submissions/${encodeURIComponent(id)}/review`, jsonRequest('POST', { decision, note: note || undefined }, csrfToken)),
}
