import type { RunEstimate, RunSpec, RunState, AccountRow, ArticleDetail, ArticleQueue, ControlSettings, ControlState, ImageLabel, AccidentRecord, Role, Session } from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...init })
  if (!response.ok) {
    const body = await response.json().catch(() => undefined) as { detail?: unknown } | undefined
    const raw = body?.detail
    const detail = typeof raw === 'string' ? raw
      : Array.isArray(raw) ? raw.map((item: { loc?: unknown[]; msg?: string }) => `${(item.loc ?? []).slice(1).join('.')}: ${(item.msg ?? '').replace(/^Value error, /, '')}`).join('; ')
      : undefined
    throw new Error(detail || `${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

function send(method: string, value: unknown, csrf?: string): RequestInit {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (csrf) headers['X-CSRF-Token'] = csrf
  return { method, headers, body: value === undefined ? undefined : JSON.stringify(value) }
}

export type LabelBody = { accidents: AccidentRecord[]; images: ImageLabel[]; unusable: boolean; notes: string }

export const api = {
  me: () => request<Session>('/api/x/me'),
  login: (username: string, password: string) => request<Session>('/api/x/login', send('POST', { username, password })),
  logout: (csrf: string) => request<{ ok: boolean }>('/api/x/logout', send('POST', undefined, csrf)),
  articles: () => request<ArticleQueue>('/api/x/articles'),
  article: (id: string) => request<ArticleDetail>(`/api/x/articles/${encodeURIComponent(id)}`),
  saveLabel: (id: string, body: LabelBody, csrf: string) => request<{ revision: number }>(`/api/x/labels/${encodeURIComponent(id)}`, send('PUT', body, csrf)),
  accounts: () => request<AccountRow[]>('/api/x/admin/accounts'),
  saveAccount: (name: string, roles: Role[], password: string | undefined, disabled: boolean | undefined, csrf: string) =>
    request<AccountRow>(`/api/x/admin/accounts/${encodeURIComponent(name)}`, send('PUT', { roles, password, disabled }, csrf)),
  control: () => request<ControlState>('/api/x/admin/control'),
  saveControl: (settings: ControlSettings, csrf: string) => request<ControlState>('/api/x/admin/control', send('PUT', settings, csrf)),
  savePricing: (pricing: ControlSettings['pricing'], csrf: string) => request<unknown>('/api/x/admin/pricing', send('PUT', { pricing }, csrf)),
  estimateRun: (spec: RunSpec, csrf: string) => request<RunEstimate>('/api/x/admin/runs/estimate', send('POST', spec, csrf)),
  startRun: (spec: RunSpec, csrf: string) => request<RunState>('/api/x/admin/runs', send('POST', spec, csrf)),
  runs: () => request<RunState[]>('/api/x/admin/runs'),
  cancelRun: (id: string, csrf: string) => request<{ cancelled: boolean }>(`/api/x/admin/runs/${encodeURIComponent(id)}/cancel`, send('POST', undefined, csrf)),
  setKey: (provider: string, key: string | null, csrf: string) => request<Pick<ControlState, 'keys'>>(`/api/x/admin/keys/${provider}`, send('PUT', { key }, csrf)),
}
