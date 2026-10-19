import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { Annotate } from './Annotate'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

test('asks for sign-in when there is no session', async () => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 401, statusText: 'Unauthorized', json: () => Promise.resolve({ detail: 'Reviewer login required' }) })) as unknown as typeof fetch)
  render(<Annotate />)
  await waitFor(() => expect(screen.getByText('Annotator sign-in')).toBeInTheDocument())
  expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
})

test('shows the pair queue for a signed-in annotator', async () => {
  const queue = { annotator: 'hamim', total: 1, labeled: 0, items: [{ item_id: 'p_1', my_label: null, left: { id: 'a', title: 'Bus hits truck', publisher: 'Daily', url: null, published_at: '2026-01-01', text: 'Left text' }, right: { id: 'b', title: 'Truck hit by bus', publisher: 'Post', url: null, published_at: '2026-01-01', text: 'Right text' } }] }
  const fetchMock = vi.fn((path: string) => Promise.resolve({ ok: true, json: () => Promise.resolve(path.includes('/api/annotate/items') ? queue : { username: 'hamim', csrf_token: 'tok' }) }))
  vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)
  render(<Annotate />)
  await waitFor(() => expect(screen.getByText('Bus hits truck')).toBeInTheDocument())
  expect(screen.getByText('0/1 labelled')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Submit label' })).toBeDisabled()
})
