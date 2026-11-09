import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from './App'

vi.mock('./components/MapView', () => ({ MapView: () => <div data-testid="map" /> }))

const publicRoutes = (path: string) => {
  if (path.endsWith('/public/overview')) return { labelling_open: true, articles: 244, images: 600, articles_with_images: 236, top_publishers: [['The Daily Star', 20]], languages: [['en', 200]], labelling: { annotators: 4, articles_with_1plus_labels: 0, articles_with_3plus_labels: 0, labels_submitted: 0 } }
  if (path.endsWith('/public/sources')) return { locked: true, message: 'locked' }
  if (path.includes('/public/incidents.geojson')) return { locked: false, type: 'FeatureCollection', meta: { source: 'grouped', records: 3, mapped: 3, verified: false }, features: [
    { type: 'Feature', geometry: { type: 'Point', coordinates: [90.4, 23.8] }, properties: { kind: 'incident', incident_id: 'i1', headline: 'Bus crash', summary: 's', killed_n: 12, year: 2025, vehicle_main: 'bus', n_articles: 2, articles: [] } },
    { type: 'Feature', geometry: { type: 'Point', coordinates: [91.1, 22.9] }, properties: { kind: 'incident', incident_id: 'i2', headline: 'Truck crash', summary: 's', killed_n: 3, year: 2026, vehicle_main: 'truck', n_articles: 1, articles: [] } },
    { type: 'Feature', geometry: { type: 'Point', coordinates: [36.8, -1.3] }, properties: { kind: 'incident', incident_id: 'i3', headline: 'Matatu crash', summary: 's', killed_n: 15, year: 2026, vehicle_main: 'car', n_articles: 1, articles: [] } }] }
  if (path.endsWith('/public/articles')) return { locked: false, articles: [{ id: 'abc123', title: 'Six killed near Kabirhat', publisher: 'BSS', language: 'en', published_at: '2025-11-04', annotations: 1, models_with_result: 1 }] }
  if (path.endsWith('/public/articles/abc123')) return { id: 'abc123', url: 'https://x.test/a', title: 'Six killed near Kabirhat', publisher: 'BSS', published_at: '2025-11-04', language: 'en', markdown: 'Six people were killed.', images: [], locked: false,
    annotators: [{ annotator: 'Annotator A', unusable: false, notes: '', revision: 1, images: [], accidents: [{ accident: true, fatalities: 6, casualities: 6, vehicles: ['truck'], date: '2025-11-04', country: 'Bangladesh', location: 'Kabirhat', 'longitude and latitude': null, evidences: [] }] }],
    models: [{ config_id: 'deepseek__deepseek-flash__markdown__txt', spec: { provider: 'deepseek', model: 'deepseek-flash', input_set: 'markdown', with_images: false }, status: 'ok', accidents: [{ accident: true, fatalities: 5, casualities: 6, vehicles: ['truck'], date: '2025-11-04', country: 'Bangladesh', location: 'Kabirhat', 'longitude and latitude': null, evidences: [] }], raw_text: '{"accidents": []}', quality: { quotes: 2, verbatim: 2 } }] }
  if (path.endsWith('/public/grouping')) return { generated_utc: '2026-11-09T07:51:00+00:00', title: 'Same-accident grouping benchmark', reading_note: 'The reference groups are checked by people; all numbers are agreement.',
    design: { articles: 244, sampled_pairs: 973, positive_pairs: 232, negative_pairs: 741, population_by_stratum: { positive: 232, easy: 28773 }, pairs_sha256: 'bc70f31248f3a2d0', decision_rule: 'SAME only if both orders say same_incident.' },
    model: { provider: 'deepseek', model: 'deepseek-flash', thinking: 'default' }, limitations: ['The reference groups come from an LLM browser agent.'], reproduce: 'mgeoai x group-benchmark --root <dir> --yes',
    methods: [{ method: 'pair-full', precision: 1, recall: 0.991, f1: 0.996, ci95: { precision: [1, 1], recall: [0.98, 1], f1: [0.99, 1] }, false_same_rate: { hard_decoy: 0, hard_near: 0, hard_similar: 0, easy: 0 }, recall_cross_language: 0.981, recall_toll_differs: 0.968, order_inconsistent: 0.004, uncertain_rate: 0.005, pairs_missing: 0 },
      { method: 'cluster-cards run0', precision: 1, recall: 1, f1: 1, ci95: { precision: [1, 1], recall: [1, 1], f1: [1, 1] }, false_same_rate: { hard_decoy: 0, hard_near: 0, hard_similar: 0, easy: 0 }, recall_cross_language: 1, recall_toll_differs: 1, order_inconsistent: null, uncertain_rate: null, pairs_missing: 0, cluster: { pair_f1_all: 1, bcubed_f1: 1, ari: 1, clusters: 100, true_groups: 100, groups_recovered_exactly: 100, clusters_merging_groups: 0, groups_split: 0 } }] }
  if (path.endsWith('/public/coverage.geojson')) return { type: 'FeatureCollection', features: [] }
  return undefined
}

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

beforeEach(() => { window.history.pushState({}, '', '/') })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('App shell', () => {
  it('shows the open map and stats without an account, and hides staff tabs', async () => {
    vi.stubGlobal('fetch', vi.fn((path: string) => { const body = publicRoutes(path); return body ? json(body) : json({ detail: 'Sign-in required' }, 401) }))
    render(<App />)
    expect(await screen.findByTestId('map')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Annotate' })).toBeNull()
    expect(screen.queryByRole('tab', { name: 'Control panel' })).toBeNull()
    expect(screen.getByText(/not incident locations/i)).toBeInTheDocument()
  })

  it('sends a signed-out visitor from /annotate to the sign-in form, and / stays the map', async () => {
    const signedOut = vi.fn((path: string) => { const body = publicRoutes(path); return body ? json(body) : json({ detail: 'Sign-in required' }, 401) })
    vi.stubGlobal('fetch', signedOut)
    window.history.pushState({}, '', '/annotate')
    render(<App />)
    expect(await screen.findByRole('heading', { name: /sign in/i })).toBeInTheDocument()
    expect(screen.queryByTestId('map')).toBeNull()
  })

  it('opens the sign-in form from the map page and returns to the map after sign-in', async () => {
    vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => {
      const open = publicRoutes(path)
      if (open) return json(open)
      if (path.endsWith('/login') && init?.method === 'POST') return json({ username: 'viewer', roles: ['reviewer'], disabled: false, csrf_token: 't' })
      return json({ detail: 'Sign-in required' }, 401)
    }))
    render(<App />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Sign in' }))
    expect(window.location.pathname).toBe('/login')
    await user.type(await screen.findByLabelText('Username'), 'viewer')
    await user.type(screen.getByLabelText('Password'), 'x')
    await user.click(screen.getAllByRole('button', { name: /sign in/i }).at(-1)!)
    expect(await screen.findByTestId('map')).toBeInTheDocument()
    expect(window.location.pathname).toBe('/')
  })

  it('shows an article with its link, text, annotator and model outputs side by side', async () => {
    vi.stubGlobal('fetch', vi.fn((path: string) => path.endsWith('/me') ? json({ detail: 'Sign-in required' }, 401) : json(publicRoutes(path) ?? { detail: 'no' }, publicRoutes(path) ? 200 : 404)))
    window.history.pushState({}, '', '/articles/abc123')
    render(<App />)
    expect(await screen.findByRole('link', { name: 'original article' })).toHaveAttribute('href', 'https://x.test/a')
    expect(await screen.findByText('Six people were killed.')).toBeInTheDocument()
    expect(screen.queryByText(/gold/i)).toBeNull()  // no gold concept anywhere in the article view
    expect(screen.getByText(/1 annotation\(s\)/)).toBeInTheDocument()
    expect(screen.getAllByText('Annotator A').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/deepseek-flash/).length).toBeGreaterThan(0)
    expect(screen.queryByRole('tab', { name: 'Annotate' })).toBeNull()
  })

  it('publishes the grouping benchmark with its caveat and no article identifiers', async () => {
    vi.stubGlobal('fetch', vi.fn((path: string) => path.endsWith('/me') ? json({ detail: 'Sign-in required' }, 401) : json(publicRoutes(path) ?? { detail: 'no' })))
    window.history.pushState({}, '', '/grouping')
    render(<App />)
    expect(await screen.findByText(/checked by people/)).toBeInTheDocument()
    expect(screen.getByText('pair-full')).toBeInTheDocument()
    expect(screen.getAllByText('cluster-cards run0')).toHaveLength(2)  // one row in each table
    expect(screen.getByText(/mgeoai x group-benchmark/)).toBeInTheDocument()
    expect(screen.getByText('bc70f31248')).toBeInTheDocument()
  })

  it('shows a full-screen incident map with filters and a legend, and no side menu', async () => {
    vi.stubGlobal('fetch', vi.fn((path: string) => {
      if (path.endsWith('/me')) return json({ detail: 'Sign-in required' }, 401)
      if (path.endsWith('/public/sources')) return json({ locked: false, sources: ['grouped', 'deepseek__deepseek-flash__markdown__txt'] })
      return json(publicRoutes(path) ?? { detail: 'no' })
    }))
    render(<App />)
    const user = userEvent.setup()
    expect(await screen.findByTestId('map')).toBeInTheDocument()
    expect(await screen.findByText(/incidents shown/)).toHaveTextContent('3 incidents shown')
    expect(screen.getByText(/30/)).toBeInTheDocument()  // 12 + 3 + 15 people killed
    expect(screen.queryByText('Top publishers')).toBeNull()  // the old side menu is gone
    expect(document.querySelector('aside')).toBeNull()
    await user.click(screen.getByRole('button', { name: '2026' }))
    await waitFor(() => expect(screen.getByText(/incidents shown/)).toHaveTextContent(/^2 incidents shown/))
    await user.selectOptions(screen.getByLabelText('Killed at least'), '5')
    await waitFor(() => expect(screen.getByText(/incidents shown/)).toHaveTextContent(/^1 incidents shown/))
    await user.selectOptions(screen.getByLabelText('Colour by'), 'vehicle')
    expect(screen.getByText(/truck \/ pickup/)).toBeInTheDocument()
    expect(screen.getByLabelText('Legend')).toHaveTextContent('Circle size = people killed')
  })

  it('shows a lock notice on the score tabs while labelling is open', async () => {
    vi.stubGlobal('fetch', vi.fn((path: string) => path.endsWith('/me') ? json({ detail: 'Sign-in required' }, 401) : json(publicRoutes(path) ?? { locked: true, message: 'locked' })))
    render(<App />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('tab', { name: 'LLM models' }))
    expect(await screen.findByText(/model performance locked/i)).toBeInTheDocument()
  })

  it('shows only the Annotate tab to annotators and the control panel to admins', async () => {
    vi.stubGlobal('fetch', vi.fn((path: string) => path.endsWith('/me')
      ? json({ username: 'ann', roles: ['annotator'], disabled: false, csrf_token: 't' })
      : json(publicRoutes(path) ?? { annotator: 'ann', total: 0, labeled: 0, articles: [] })))
    render(<App />)
    expect(await screen.findByRole('tab', { name: 'Annotate' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Control panel' })).toBeNull()
  })

  it('lets an admin set another user\'s password without ever showing it back', async () => {
    const seen: unknown[] = []
    vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => {
      const open = publicRoutes(path)
      if (open) return json(open)
      if (path.endsWith('/me')) return json({ username: 'root', roles: ['admin'], disabled: false, csrf_token: 't' })
      if (path.includes('/admin/accounts/') && init?.method === 'PUT') { seen.push(JSON.parse(String(init.body))); return json({ username: 'oishik', roles: ['annotator'], disabled: false }) }
      if (path.endsWith('/admin/accounts')) return json([{ username: 'oishik', roles: ['annotator'], disabled: false }, { username: 'root', roles: ['admin'], disabled: false }])
      if (path.endsWith('/admin/runs')) return json([])
      return json({ settings: { labelling_open: true, pricing: {}, run_token_limit: 1000, max_images_per_article: 3, run_cost_limit_usd: 5, daily_cost_limit_usd: 20, concurrency: 2, providers: Object.fromEntries(['openai', 'anthropic', 'openrouter', 'deepseek'].map((n) => [n, { model: '', base_url: '', input_cost_per_million_usd: null, output_cost_per_million_usd: null, timeout_seconds: 120, max_output_tokens: 4000, supports_images: false }])) }, keys: {} })
    }))
    render(<App />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('tab', { name: 'Control panel' }))
    const field = await screen.findByLabelText('New password for oishik')
    const button = field.parentElement!.querySelector('button')!
    expect(button).toBeDisabled()
    await user.type(field, 'short')
    expect(button).toBeDisabled()
    await user.clear(field)
    await user.type(field, 'a-much-longer-password')
    await user.click(button)
    await waitFor(() => expect(seen).toEqual([{ roles: ['annotator'], password: 'a-much-longer-password' }]))
    await waitFor(() => expect(field).toHaveValue(''))
  })

  it('explains why Start run is unavailable when the provider key was lost', async () => {
    vi.stubGlobal('fetch', vi.fn((path: string) => {
      const open = publicRoutes(path)
      if (open) return json(open)
      if (path.endsWith('/me')) return json({ username: 'root', roles: ['admin'], disabled: false, csrf_token: 't' })
      if (path.endsWith('/admin/accounts')) return json([{ username: 'root', roles: ['admin'], disabled: false }])
      if (path.endsWith('/admin/runs')) return json([])
      return json({ settings: { labelling_open: true, pricing: {}, run_token_limit: 1000, max_images_per_article: 3, run_cost_limit_usd: 5, daily_cost_limit_usd: 20, concurrency: 2, providers: Object.fromEntries(['openai', 'anthropic', 'openrouter', 'deepseek'].map((n) => [n, { model: 'deepseek-flash', base_url: '', input_cost_per_million_usd: null, output_cost_per_million_usd: null, timeout_seconds: 600, max_output_tokens: 393216, supports_images: false }])) }, keys: { deepseek: { configured: false, source: 'none' }, openrouter: { configured: false, source: 'none' }, openai: { configured: false, source: 'none' }, anthropic: { configured: false, source: 'none' } } })
    }))
    render(<App />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('tab', { name: 'Control panel' }))
    expect(await screen.findByText(/No API key is set for DeepSeek/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start run' })).toBeDisabled()
  })

  it('never renders a stored API key after it is set', async () => {
    const secret = 'sk-test-secret-value'
    const state = { settings: { labelling_open: true, pricing: {}, run_token_limit: 2000000, max_images_per_article: 3, run_cost_limit_usd: 5, daily_cost_limit_usd: 20, concurrency: 2, providers: Object.fromEntries(['openai', 'anthropic', 'openrouter', 'deepseek'].map((n) => [n, { model: '', base_url: '', input_cost_per_million_usd: null, output_cost_per_million_usd: null, timeout_seconds: 120, max_output_tokens: 4000, supports_images: false }])) }, keys: { openai: { configured: true, source: 'ui_memory' }, anthropic: { configured: false, source: 'none' }, openrouter: { configured: false, source: 'none' }, deepseek: { configured: false, source: 'none' } } }
    vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => {
      const open = publicRoutes(path)
      if (open) return json(open)
      if (path.endsWith('/me')) return json({ username: 'root', roles: ['admin'], disabled: false, csrf_token: 't' })
      if (path.includes('/admin/keys/')) { expect((init?.headers as Record<string, string>)['X-CSRF-Token']).toBe('t'); return json({ keys: state.keys }) }
      if (path.endsWith('/admin/runs')) return json([])
      if (path.endsWith('/admin/accounts')) return json([{ username: 'root', roles: ['admin'], disabled: false }])
      return json(state)
    }))
    render(<App />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('tab', { name: 'Control panel' }))
    const inputs = await screen.findAllByPlaceholderText('paste API key')
    await user.type(inputs[0], secret)
    await user.click(screen.getAllByRole('button', { name: 'Set' })[0])
    await waitFor(() => expect(screen.getByText(/ChatGPT \(OpenAI\) · set \(ui_memory\)/)).toBeInTheDocument())
    expect(document.body.innerHTML).not.toContain(secret)
  })
})
