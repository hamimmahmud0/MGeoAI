import type { Fact } from '../types'

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return 'not selected'
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    if (typeof record.count === 'number') {
      const qualifier = typeof record.qualifier === 'string' ? ` ${record.qualifier}` : ''
      return `${record.count}${qualifier}`
    }
    if (typeof record.state === 'string') return record.state.replaceAll('_', ' ')
    return JSON.stringify(value)
  }
  return String(value)
}

export function formatCasualtyFact(fact: Fact | undefined): string {
  if (!fact) return 'Not reported'
  if (fact.state === 'reported_zero') return '0'
  if (typeof fact.value === 'number') return String(fact.value)
  const alternatives = fact.conflicting_values
    .map((value) => typeof value === 'object' && value !== null ? (value as Record<string, unknown>).count : value)
    .filter((value): value is number => typeof value === 'number')
  if (alternatives.length) return `${[...new Set(alternatives)].join(' vs ')} reported`
  return fact.state.replaceAll('_', ' ')
}
