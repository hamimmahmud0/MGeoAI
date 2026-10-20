import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from './App'

vi.mock('./components/MapView', () => ({ MapView: () => <div data-testid="map" /> }))

const publicRoutes = (path: string) => {
  if (path.endsWith('/public/overview')) return { labelling_open: true, articles: 244, images: 600, articles_with_images: 236, top_publishers: [['The Daily Star', 20]], languages: [['en', 200]], labelling: { annotators: 4, articles_with_1plus_labels: 0, articles_with_3plus_labels: 0, labels_submitted: 0 } }
  if (path.endsWith('/public/sources')) return { locked: true, message: 'locked' }
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
    expect(await screen.findByText('244')).toBeInTheDocument()
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
