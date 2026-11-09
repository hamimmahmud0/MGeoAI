export const pct = (value: number | null | undefined) => (value === null || value === undefined ? '—' : `${(value * 100).toFixed(1)}%`)
