import type { MapProps } from '../types'

type Item = { id: string; title: string; publisher: string }
type Raw = MapProps & { items?: Item[] | string }

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
  box.append(el('b', `${props.country ?? 'Country'} · ${props.articles ?? items.length} article(s)`))
  box.append(el('div', 'Collection country, not an incident location', 'mg-muted'))
  for (const item of items.slice(0, 8)) {
    const row = el('div', undefined, 'mg-row')
    row.append(button(item.title, item.id), el('span', ` ${item.publisher}`, 'mg-muted'))
    box.append(row)
  }
  if ((props.articles ?? 0) > 8) box.append(el('div', `+${Number(props.articles) - 8} more: use the Articles tab`, 'mg-muted'))
  return box
}
