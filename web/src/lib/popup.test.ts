import { describe, expect, it, vi } from 'vitest'
import { buildPopup } from './popup'

describe('buildPopup', () => {
  it('shows an incident card with an article link and never injects markup from titles', () => {
    const open = vi.fn()
    const box = buildPopup({ incident_id: 'abc', title: '<img src=x onerror=alert(1)>Six killed', publisher: 'BSS', fatalities: 6, casualities: 8, verified: false, location: 'Kabirhat', source_url: 'https://x.test/a' }, open)
    expect(box.querySelector('img')).toBeNull()
    expect(box.textContent).toContain('<img src=x onerror=alert(1)>Six killed')
    expect(box.textContent).toContain('Model output, unverified')
    box.querySelector('button')!.click()
    expect(open).toHaveBeenCalledWith('abc')
    expect(box.querySelector('a')!.getAttribute('href')).toBe('https://x.test/a')
  })

  it('lists a collection country\'s articles (items may arrive as a JSON string from the map)', () => {
    const open = vi.fn()
    const items = JSON.stringify([{ id: 'a1', title: 'Bus plunges', publisher: 'DW' }, { id: 'a2', title: 'Truck overturns', publisher: 'BBC' }])
    const box = buildPopup({ country: 'Uganda', articles: 12, items }, open)
    expect(box.textContent).toContain('Uganda · 12 article(s)')
    expect(box.textContent).toContain('not an incident location')
    expect(box.textContent).toContain('+4 more')
    box.querySelectorAll('button')[1].click()
    expect(open).toHaveBeenCalledWith('a2')
  })

  it('renders a fused incident card from MapLibre-flattened properties, with sources and disagreements', () => {
    const open = vi.fn()
    const props = {
      kind: 'incident', headline: 'Bus plunges into Padma', summary: 'A bus fell into the river. <b>bold</b>', killed: 26, injured: 3, when: '2026-03-25',
      place: 'Daulatdia ferry terminal, Rajbari, Bangladesh', n_articles: 2, uncertainty_radius_km: 2, location_method: 'OpenStreetMap place centroid', fused_by: 'deepseek-flash',
      vehicles: JSON.stringify(['bus']), disagreements: JSON.stringify(['Tolls differ: 2 vs 18 vs 26']),
      articles: JSON.stringify([{ id: 'a1', title: 'At least 18 killed', publisher: 'The Daily Star', url: 'https://x.test/1' }, { id: 'a2', title: 'পদ্মায় বাস', publisher: 'Prothom Alo', url: null }]),
    }
    const box = buildPopup(props as never, open)
    expect(box.textContent).toContain('2 source article(s) grouped by an LLM')
    expect(box.textContent).toContain('A bus fell into the river. <b>bold</b>')
    expect(box.querySelectorAll('b')).toHaveLength(1)  // only the headline: summary text cannot inject markup
    expect(box.textContent).toContain('Killed: 26 · Injured: 3 · bus')
    expect(box.textContent).toContain('Tolls differ: 2 vs 18 vs 26')
    const buttons = box.querySelectorAll('button')
    expect(buttons).toHaveLength(2)
    buttons[1].click()
    expect(open).toHaveBeenCalledWith('a2')
  })
})
