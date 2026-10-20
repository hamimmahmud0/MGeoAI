import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { ModelRow } from '../types'
import { pct } from '../lib/format'
import { LockNotice } from './Lock'

const ci = (value: { value: number | null; ci95: number[] | null; n: number }) =>
  value.value === null ? '—' : `${pct(value.value)}${value.ci95 ? ` [${pct(value.ci95[0])}–${pct(value.ci95[1])}]` : ''} n=${value.n}`

export function ModelsTab() {
  const [rows, setRows] = useState<ModelRow[] | null>(null)
  const [locked, setLocked] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    api.modelScores().then((res) => (res.locked ? setLocked(true) : setRows(res.models))).catch((cause: Error) => setError(cause.message))
  }, [])
  if (error) return <p role="alert" className="p-4 text-danger">{error}</p>
  if (locked) return <LockNotice what="Model performance" />
  if (!rows) return <p className="p-4 text-muted">Loading…</p>
  if (!rows.length) return <p className="p-4 text-muted">No extraction runs yet.</p>
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4 p-4">
      {rows.map((row) => (
        <section key={row.config_id} className="panel p-4">
          <h2 className="font-bold text-primary">{row.spec.provider} · {row.spec.model} <span className="badge">{row.spec.input_set}</span> <span className="badge">{row.spec.with_images ? 'with images' : 'text only'}</span></h2>
          <p className="text-muted">{row.metrics.articles_ok} ok · {row.metrics.articles_failed} failed · {row.metrics.scored_articles} scored against gold · tokens {row.tokens.input.toLocaleString()} in / {row.tokens.output.toLocaleString()} out · cost {row.cost_usd === null ? 'unknown' : `$${row.cost_usd}`} · {row.metrics.mean_latency_ms ?? '—'} ms mean</p>
          <div className="mt-2 grid gap-4 md:grid-cols-2">
            <table className="text-left"><tbody>
              <tr><td className="label pr-4">Accident flag P / R / F1</td><td>{pct(row.metrics.accident_flag.precision)} / {pct(row.metrics.accident_flag.recall)} / {pct(row.metrics.accident_flag.f1)}</td></tr>
              <tr><td className="label pr-4">Accident count right</td><td>{ci(row.metrics.accident_count_correct)}</td></tr>
              <tr><td className="label pr-4">Fatalities MAE</td><td>{row.metrics.fatalities_mae ?? '—'}</td></tr>
              <tr><td className="label pr-4">Vehicles Jaccard</td><td>{row.metrics.vehicles_jaccard ?? '—'}</td></tr>
              <tr><td className="label pr-4">Location token overlap</td><td>{row.metrics.location_token_overlap ?? '—'}</td></tr>
              <tr><td className="label pr-4">Evidence quotes verbatim</td><td>{pct(row.metrics.evidence_quotes_verbatim.rate)} ({row.metrics.evidence_quotes_verbatim.verbatim}/{row.metrics.evidence_quotes_verbatim.quotes})</td></tr></tbody></table>
            <table className="text-left"><thead><tr className="label"><th>Field exact match</th><th>Rate [95% CI]</th></tr></thead><tbody>
              {Object.entries(row.metrics.fields_exact).map(([field, rate]) => <tr key={field} className="border-t border-line"><td className="py-1 pr-4">{field}</td><td>{ci(rate)}</td></tr>)}</tbody></table>
          </div>
          <p className="mt-2 text-muted">{row.metrics.note}</p>
        </section>))}
    </div>
  )
}
