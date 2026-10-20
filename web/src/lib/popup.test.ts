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
})
