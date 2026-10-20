import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from './App'

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('App shell', () => {
  it('shows sign-in when there is no session', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json({ detail: 'Sign-in required' }, 401)))
    render(<App />)
    expect(await screen.findByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('shows only the Annotate tab to annotators and the control panel to admins', async () => {
    vi.stubGlobal('fetch', vi.fn((path: string) => path.endsWith('/me')
      ? json({ username: 'ann', roles: ['annotator'], disabled: false, csrf_token: 't' })
      : json({ annotator: 'ann', total: 0, labeled: 0, articles: [] })))
    render(<App />)
    expect(await screen.findByRole('tab', { name: 'Annotate' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Control panel' })).toBeNull()
  })

  it('never renders a stored API key after it is set', async () => {
    const secret = 'sk-test-secret-value'
    const state = { settings: { labelling_open: true, pricing: {}, run_token_limit: 2000000, max_images_per_article: 3, run_cost_limit_usd: 5, daily_cost_limit_usd: 20, concurrency: 2, providers: Object.fromEntries(['openai', 'anthropic', 'openrouter', 'deepseek'].map((n) => [n, { model: '', base_url: '', input_cost_per_million_usd: null, output_cost_per_million_usd: null, timeout_seconds: 120, max_output_tokens: 4000, supports_images: false }])) }, keys: { openai: { configured: true, source: 'ui_memory' }, anthropic: { configured: false, source: 'none' }, openrouter: { configured: false, source: 'none' }, deepseek: { configured: false, source: 'none' } } }
    vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => {
      if (path.endsWith('/me')) return json({ username: 'root', roles: ['admin'], disabled: false, csrf_token: 't' })
      if (path.includes('/admin/keys/')) { expect((init?.headers as Record<string, string>)['X-CSRF-Token']).toBe('t'); return json({ keys: state.keys }) }
      if (path.endsWith('/admin/runs')) return json([])
      if (path.endsWith('/admin/accounts')) return json([{ username: 'root', roles: ['admin'], disabled: false }])
      return json(state)
    }))
    render(<App />)
    const user = userEvent.setup()
    const inputs = await screen.findAllByPlaceholderText('paste API key')
    await user.type(inputs[0], secret)
    await user.click(screen.getAllByRole('button', { name: 'Set' })[0])
    await waitFor(() => expect(screen.getByText(/ChatGPT \(OpenAI\) · set \(ui_memory\)/)).toBeInTheDocument())
    expect(document.body.innerHTML).not.toContain(secret)
  })
})
