import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IncidentCard } from './IncidentCard'

const rec = (fatalities: number, extra = {}) => ({ accident: true, fatalities, casualities: fatalities + 1, vehicles: ['bus'], date: '2026-03-25', country: 'Bangladesh', location: 'Daulatdia', 'longitude and latitude': null, evidences: [], ...extra })
const detail = (id: string, human: number, model: number) => ({
  id, url: null, title: id, publisher: id, published_at: null, language: 'en', markdown: '', images: [], locked: false,
  annotators: [{ annotator: 'Annotator A', unusable: false, notes: '', revision: 1, images: [], accidents: [rec(human)] }],
  models: [{ config_id: 'm1', spec: { provider: 'deepseek', model: 'deepseek-flash', input_set: 'markdown', with_images: false }, status: 'ok', accidents: [rec(model)] }],
})
const props = {
  kind: 'incident' as const, incident_id: 'i1', headline: 'Bus plunges', summary: 'A bus fell.', killed: 18, injured: 3, when: '2026-03-25', place: 'Daulatdia',
  vehicles: ['bus'], n_articles: 3, articles: [{ id: 'a', title: 'A', publisher: 'Star', url: 'https://x/a', published_at: null, language: 'en' }, { id: 'b', title: 'B', publisher: 'Alo', url: null, published_at: null, language: 'bn' }, { id: 'c', title: 'C', publisher: 'BSS', url: null, published_at: null, language: 'en' }],
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('IncidentCard', () => {
  it('has separate summary, fields and sources sections and switches between annotation and model output', async () => {
    const all: Record<string, unknown> = { a: detail('a', 18, 18), b: detail('b', 2, 18), c: detail('c', 18, 26) }
    vi.stubGlobal('fetch', vi.fn((path: string) => Promise.resolve(new Response(JSON.stringify(all[path.split('/').pop() as string]), { status: 200, headers: { 'Content-Type': 'application/json' } }))))
    render(<IncidentCard props={props} onOpen={() => undefined} onClose={() => undefined} />)
    for (const name of ['Summary', 'Extracted fields', 'Sources']) expect(screen.getByRole('region', { name })).toBeInTheDocument()
    const fields = screen.getByRole('region', { name: 'Extracted fields' })
    const select = await within(fields).findByRole('combobox', { name: 'Source of extracted fields' })
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['Annotation · Annotator A', 'Model output · deepseek-flash'])
    // annotation view: the Alo article says 2 killed, the odd one out
    expect(within(fields).getByRole('cell', { name: '2' })).toHaveClass('bg-warning-soft')
    await userEvent.selectOptions(select, 'm:m1')
    expect(within(fields).getByRole('cell', { name: '26' })).toHaveClass('bg-warning-soft')
    expect(within(fields).queryByRole('cell', { name: '2' })).toBeNull()
  })

  it('explains when annotations and model output are hidden', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({ ...detail('a', 1, 1), locked: true }), { status: 200, headers: { 'Content-Type': 'application/json' } }))))
    render(<IncidentCard props={props} onOpen={() => undefined} onClose={() => undefined} />)
    expect(await screen.findByText(/hidden while labelling is open/)).toBeInTheDocument()
  })
})
