import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { pct } from '../lib/format'
import type { GroupingSummary } from '../types'
import { Stat } from './Lock'

const ci = (range: number[] | undefined) => (range && range.every((value) => Number.isFinite(value)) ? ` [${Math.round(range[0] * 100)}–${Math.round(range[1] * 100)}]` : '')
const STRATA: [string, string][] = [['hard_decoy', 'look-alike crash'], ['hard_near', 'same country, ±4 d'], ['hard_similar', 'similar text'], ['easy', 'random']]

export function GroupingTab() {
  const [data, setData] = useState<GroupingSummary | null>(null)
  const [missing, setMissing] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    api.grouping().then((res) => ('available' in res && res.available === false ? setMissing(true) : setData(res as GroupingSummary))).catch((cause: Error) => setError(cause.message))
  }, [])
  if (error) return <p role="alert" className="p-4 text-danger">{error}</p>
  if (missing) return <p className="p-4 text-muted">The grouping benchmark has not been published yet.</p>
  if (!data) return <p className="p-4 text-muted">Loading…</p>
  const clusters = data.methods.filter((method) => method.cluster)
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4 p-4">
      <div><h1 className="text-base font-bold">{data.title}</h1>
        <p className="text-muted">Can an LLM tell which news articles report the same accident? Model: {data.model.provider} {data.model.model}, thinking {data.model.thinking} · generated {data.generated_utc.slice(0, 16).replace('T', ' ')} UTC</p></div>
      <div role="note" className="panel border-warning-line bg-warning-soft p-3 text-warning">{data.reading_note}</div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Stat label="Articles" value={data.design.articles} /><Stat label="Sampled pairs" value={data.design.sampled_pairs} hint={`${data.design.positive_pairs} same / ${data.design.negative_pairs} different`} />
        <Stat label="Possible pairs" value={Object.values(data.design.population_by_stratum).reduce((a, b) => a + b, 0).toLocaleString()} /><Stat label="Pair set fingerprint" value={data.design.pairs_sha256.slice(0, 10)} hint="frozen before any model call" />
      </div>
      <section className="panel overflow-x-auto p-3"><h2 className="label mb-2">Pair methods and clustering on the sampled pairs (estimates re-weighted to all pairs; [95% interval])</h2>
        <table className="w-full text-left"><thead><tr className="label"><th className="py-1">Method</th><th>Precision</th><th>Recall</th><th>F1</th>{STRATA.map(([, label]) => <th key={label}>Wrongly SAME: {label}</th>)}<th>Recall: cross-language</th><th>Recall: toll differs</th></tr></thead>
          <tbody>{data.methods.map((method) => (
            <tr key={method.method} className="border-t border-line"><td className="py-1 pr-2">{method.method}</td><td>{pct(method.precision)}{ci(method.ci95.precision)}</td><td>{pct(method.recall)}{ci(method.ci95.recall)}</td>
              <td><b>{pct(method.f1)}</b>{ci(method.ci95.f1)}</td>{STRATA.map(([key]) => <td key={key}>{pct(method.false_same_rate[key])}</td>)}<td>{pct(method.recall_cross_language)}</td><td>{pct(method.recall_toll_differs)}</td></tr>))}</tbody></table>
        <p className="mt-2 text-muted">Decision rule (fixed in advance): {data.design.decision_rule}</p></section>
      {clusters.length > 0 && <section className="panel overflow-x-auto p-3"><h2 className="label mb-2">Clustering over all {data.design.articles} articles</h2>
        <table className="w-full text-left"><thead><tr className="label"><th className="py-1">Run</th><th>Pair F1 (all pairs)</th><th>B-cubed F1</th><th>ARI</th><th>Clusters / true groups</th><th>Groups recovered exactly</th><th>Clusters merging groups</th><th>Groups split</th></tr></thead>
          <tbody>{clusters.map((method) => method.cluster && (
            <tr key={method.method} className="border-t border-line"><td className="py-1 pr-2">{method.method}</td><td>{pct(method.cluster.pair_f1_all)}</td><td>{pct(method.cluster.bcubed_f1)}</td><td>{method.cluster.ari.toFixed(3)}</td>
              <td>{method.cluster.clusters} / {method.cluster.true_groups}</td><td>{method.cluster.groups_recovered_exactly}</td><td>{method.cluster.clusters_merging_groups}</td><td>{method.cluster.groups_split}</td></tr>))}</tbody></table></section>}
      <section className="panel p-3"><h2 className="label mb-2">Limitations</h2><ul className="list-disc pl-5">{data.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
        <p className="mt-2 text-muted">Reproduce: <code>{data.reproduce}</code></p></section>
    </div>
  )
}
