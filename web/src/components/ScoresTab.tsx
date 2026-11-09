import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { AnnotationScores } from '../types'
import { pct } from '../lib/format'
import { LockNotice, Stat } from './Lock'

export function ScoresTab() {
  const [scores, setScores] = useState<AnnotationScores | null>(null)
  const [locked, setLocked] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    api.annotationScores().then((res) => (res.locked ? setLocked(true) : setScores(res))).catch((cause: Error) => setError(cause.message))
  }, [])
  if (error) return <p role="alert" className="p-4 text-danger">{error}</p>
  if (locked) return <LockNotice what="Annotation scores" />
  if (!scores) return <p className="p-4 text-muted">Loading…</p>
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 p-4">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Stat label="Articles" value={scores.articles_total} /><Stat label="Annotated" value={scores.articles_with_1plus_labels} hint="one annotation per article is enough" />
        <Stat label="Labelled by 2+ people" value={scores.articles_with_2plus_labels} hint="used for the agreement figures" />
        <Stat label="Accident flag α" value={scores.accident_flag_alpha === null ? '—' : scores.accident_flag_alpha.toFixed(3)} hint="≥0.80 good · 0.667–0.80 tentative" />
      </div>
      <section className="panel p-4"><h2 className="label mb-2">Exact agreement between annotator pairs (single-accident articles)</h2>
        <table className="w-full text-left"><thead><tr className="label"><th>Field</th><th>Agreement</th><th>Pairs</th></tr></thead><tbody>
          {Object.entries(scores.field_exact_agreement).map(([field, row]) => <tr key={field} className="border-t border-line"><td className="py-1">{field}</td><td>{pct(row.rate)}</td><td>{row.pairs}</td></tr>)}</tbody></table></section>
      <section className="panel p-4"><h2 className="label mb-2">Cohen κ for the accident flag</h2>
        <table className="w-full text-left"><thead><tr className="label"><th>Pair</th><th>κ</th><th>Articles</th></tr></thead><tbody>
          {Object.entries(scores.accident_flag_cohen_kappa).map(([pair, row]) => <tr key={pair} className="border-t border-line"><td className="py-1">{pair.replace('|', ' ↔ ')}</td><td>{row.kappa === null ? '—' : row.kappa.toFixed(3)}</td><td>{row.articles}</td></tr>)}</tbody></table></section>
      <p className="text-muted">Agreement is measured only on the articles that two or more people labelled; every article needs just one annotation.</p>
    </div>
  )
}
