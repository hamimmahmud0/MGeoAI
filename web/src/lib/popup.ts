import type { MapProps } from '../types'

type Item = { id: string; title: string; publisher: string }
type Source = { id: string; title: string | null; publisher: string | null; url: string | null; published_at: string | null }
type Raw = Omit<MapProps, 'articles'> & { items?: Item[] | string; articles?: number | Source[] | string }
const parsed = <T,>(value: unknown): T | undefined => (typeof value === 'string' ? (JSON.parse(value) as T) : (value as T | undefined))

const el = <K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, className?: string) => {
  const node = document.createElement(tag)
  if (text !== undefined) node.textContent = text // never innerHTML: titles come from untrusted pages
  if (className) node.className = className
  return node
}

/** Hover card for a map point. Built with textContent only, so page titles cannot inject markup. */
export function buildPopup(props: Raw, open: (articleId: string) => void): HTMLElement {
  const box = el('div', undefined, 'mg-popup')
  const button = (label: string, id: string) => {
    const link = el('button', label, 'mg-popup-link')
    link.type = 'button'
    link.addEventListener('click', () => open(id))
    return link
  }
  if (props.kind === 'incident') {
    const sources = parsed<Source[]>(props.articles) ?? []
    const disagreements = parsed<string[]>(props.disagreements) ?? []
    const vehicles = parsed<string[]>(props.vehicles) ?? []
    box.append(el('b', props.headline ?? 'Incident'))
    box.append(el('div', `${props.n_articles ?? sources.length} source article(s) grouped by an LLM · fused summary by ${props.fused_by ?? 'DeepSeek'} · unverified`, 'mg-badge'))
    box.append(el('div', props.summary ?? ''))
    box.append(el('div', `Killed: ${props.killed ?? 'unknown'} · Injured: ${props.injured ?? 'unknown'}${vehicles.length ? ` · ${vehicles.join(', ')}` : ''}`))
    box.append(el('div', `When: ${props.when ?? 'unknown'} · Place: ${props.place ?? 'unknown'}`))
    box.append(el('div', `${props.location_method ?? ''} · radius ${props.uncertainty_radius_km ?? '?'} km`, 'mg-muted'))
    if (disagreements.length) {
      box.append(el('div', 'Sources disagree on:', 'mg-muted'))
      for (const text of disagreements.slice(0, 3)) box.append(el('div', `• ${text}`, 'mg-muted'))
    }
    box.append(el('div', 'Sources:', 'mg-muted'))
    for (const source of sources) {
      const row = el('div', undefined, 'mg-row')
      row.append(button(`${source.publisher ?? ''}: ${source.title ?? source.id}`, source.id))
      box.append(row)
    }
    return box
  }
  if (props.incident_id && props.title) {
    box.append(el('b', props.title), el('div', props.publisher ?? '', 'mg-muted'))
    box.append(el('div', `${props.verified ? 'Human gold' : 'Model output, unverified'}`, 'mg-badge'))
    box.append(el('div', `Killed: ${props.fatalities ?? 'unknown'} · Killed+injured: ${props.casualities ?? 'unknown'}`))
    box.append(el('div', `Date: ${props.date ?? 'unknown'}`))
    box.append(el('div', `Place: ${props.location ?? 'unknown'}${props.country ? `, ${props.country}` : ''}`))
    box.append(button('Open article details', String(props.incident_id)))
    if (props.source_url) {
      const link = el('a', 'Original article', 'mg-popup-link')
      link.href = String(props.source_url)
      link.target = '_blank'
      link.rel = 'noreferrer noopener'
      box.append(link)
    }
    return box
  }
  const raw = props.items
  const items: Item[] = typeof raw === 'string' ? (JSON.parse(raw) as Item[]) : raw ?? []
  box.append(el('b', `${props.country ?? 'Country'} · ${typeof props.articles === 'number' ? props.articles : items.length} article(s)`))
  box.append(el('div', 'Collection country, not an incident location', 'mg-muted'))
  for (const item of items.slice(0, 8)) {
    const row = el('div', undefined, 'mg-row')
    row.append(button(item.title, item.id), el('span', ` ${item.publisher}`, 'mg-muted'))
    box.append(row)
  }
  const count = typeof props.articles === 'number' ? props.articles : 0
  if (count > 8) box.append(el('div', `+${count - 8} more: use the Articles tab`, 'mg-muted'))
  return box
}
