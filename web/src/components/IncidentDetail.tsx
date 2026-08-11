import { useEffect, useState } from 'react'
import { AlertTriangle, BookOpen, ExternalLink, FileSearch, MapPin, X } from 'lucide-react'
import { api } from '../lib/api'
import { formatCasualtyFact, formatValue } from '../lib/incidentPresentation'
import type { Incident, IncidentEvidence } from '../types'
import { DetailedIncidentReview } from './DetailedIncidentReview'

export function IncidentDetail({ incident, onClose, onInspectSource }: { incident: Incident; onClose: () => void; onInspectSource: (id: string) => void }) {
  const fatality = incident.facts.find((item) => item.field === 'fatalities')
  const injury = incident.facts.find((item) => item.field === 'injuries')
  const [evidence, setEvidence] = useState<IncidentEvidence>()
  const [evidenceError, setEvidenceError] = useState('')
  const [reviewOpen, setReviewOpen] = useState(false)

  useEffect(() => {
    let active = true
    setEvidence(undefined)
    setEvidenceError('')
    api.evidence(incident.incident_id)
      .then((result) => { if (active) setEvidence(result) })
      .catch((reason: Error) => { if (active) setEvidenceError(reason.message) })
    return () => { active = false }
  }, [incident.incident_id])

  return (
    <aside className="fixed inset-y-0 right-0 z-30 flex w-full max-w-[560px] flex-col border-l border-line bg-surface shadow-xl" aria-label="Incident detail" aria-live="polite">
      <header className="flex items-start justify-between border-b border-line px-6 py-5">
        <div><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-primary">Incident record</p><h2 className="text-xl font-semibold leading-snug">{incident.title}</h2></div>
        <button onClick={onClose} className="rounded p-2 text-muted hover:bg-canvas" aria-label="Close incident detail"><X size={19} /></button>
      </header>
      <div className="flex-1 space-y-7 overflow-y-auto px-6 py-5">
        {incident.data_quality_warnings.some((item) => item.includes('RECORDED')) && <div className="flex gap-3 border border-warning-line bg-warning-soft p-3 text-sm text-warning"><AlertTriangle size={18} className="mt-0.5 shrink-0" /><span>Recorded demo output—not a live model fusion or independent verification.</span></div>}
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Fused summary</h3>
          <p className="text-sm leading-6">{incident.human_summary}</p>
          <div className="mt-4 rounded border border-line bg-canvas p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">Important information</p>
            <ul className="mt-3 space-y-2 text-sm leading-5">
              <li><b>When and where:</b> {incident.event_time.start ? new Date(incident.event_time.start).toLocaleDateString() : 'Date not reported'} · {incident.geolocation.display_name || 'location unresolved'} ({incident.geolocation.granularity} precision).</li>
              <li><b>Reported impact:</b> {casualtySummary(incident)}.</li>
              <li><b>Vehicles or parties:</b> {[...incident.vehicles, ...incident.involved_parties].join(', ') || 'Not reported'}.</li>
              <li><b>Traffic effect:</b> {incident.congestion_delay || incident.obstruction || 'No explicit traffic effect reported'}.</li>
              <li><b>Evidence basis:</b> {incident.independent_source_count} independent group(s), {incident.source_ids.length} source record(s), and {incident.evidence_ids.length} cited evidence item(s).</li>
            </ul>
          </div>
          <button onClick={() => setReviewOpen(true)} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90"><BookOpen size={16} />Open detailed fused review</button>
        </section>
        <section className="grid grid-cols-2 gap-3">
          <Data label="When" value={incident.event_time.start ? new Date(incident.event_time.start).toLocaleDateString() : 'Not reported'} />
          <Data label="Severity" value={incident.severity} />
          <Data label="Fatalities" value={formatCasualtyFact(fatality)} />
          <Data label="Injuries" value={formatCasualtyFact(injury)} />
        </section>
        <section><h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Location and precision</h3><div className="flex gap-3 rounded border border-line p-3"><MapPin size={18} className="mt-0.5 shrink-0 text-primary" /><div><p className="text-sm font-medium">{incident.geolocation.display_name || 'Unmapped'}</p><p className="mt-1 text-xs leading-5 text-muted">{incident.geolocation.granularity} precision · {Math.round(incident.geolocation.confidence * 100)}% confidence{incident.geolocation.uncertainty_radius_km ? ` · ~${incident.geolocation.uncertainty_radius_km} km uncertainty radius` : ''}</p>{incident.geolocation.ambiguity_reason && <p className="mt-2 text-xs text-muted">{incident.geolocation.ambiguity_reason}</p>}{incident.geolocation.latitude !== undefined && incident.geolocation.longitude !== undefined && <a className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline" href={`https://www.openstreetmap.org/?mlat=${incident.geolocation.latitude}&mlon=${incident.geolocation.longitude}#map=15/${incident.geolocation.latitude}/${incident.geolocation.longitude}`} target="_blank" rel="noreferrer"><ExternalLink size={13} />Inspect nearby roads</a>}</div></div></section>
        <section><h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Traffic effect</h3><p className="text-sm">{incident.congestion_delay || 'Not reported; no congestion inferred from the crash alone.'}</p></section>
        <section><h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Sentiment by aspect</h3>{Object.keys(incident.sentiment.by_aspect).length ? Object.entries(incident.sentiment.by_aspect).map(([aspect, values]) => <div key={aspect} className="mb-2 flex items-center justify-between border-b border-line pb-2 text-sm"><span>{aspect.replaceAll('_', ' ')}</span><span className="text-muted">{Object.entries(values).map(([key, value]) => `${key} ${value}`).join(' · ')}</span></div>) : <p className="text-sm text-muted">{incident.sentiment.coverage_note}</p>}</section>
        {incident.facts.some((fact) => fact.conflicting_values.length) && <section><h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Conflicts and alternatives</h3>{incident.facts.filter((fact) => fact.conflicting_values.length).map((fact) => <p className="mb-2 text-sm" key={fact.field}><b>{fact.field}:</b> selected {formatValue(fact.value)}; alternatives {fact.conflicting_values.map(formatValue).join(', ')}</p>)}</section>}
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Evidence and provenance</h3>
          <p className="text-sm">{incident.independent_source_count} independent source group(s), {incident.evidence_ids.length} cited evidence item(s).</p>
          {!evidence && !evidenceError && <p className="mt-3 text-xs text-primary">Loading cited evidence…</p>}
          {evidenceError && <p role="alert" className="mt-3 text-xs text-danger">Evidence content could not be loaded: {evidenceError}</p>}
          {evidence && <div className="mt-3 space-y-3">{evidence.items.map((item) => {
            const source = evidence.sources[item.source_id]
            return <article key={item.evidence_id} className="rounded border border-line bg-canvas p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2"><span className="badge">{item.assertion_type.replaceAll('_', ' ')}</span><span className="badge">{item.modality}</span><span className="ml-auto text-[11px] text-muted">{Math.round(item.extraction_confidence * 100)}% extraction confidence</span></div>
              <p className="text-sm leading-6">{item.claim_text}</p>
              {item.claimant && <p className="mt-2 text-xs text-muted">Attributed to {item.claimant}{item.claimant_role ? ` (${item.claimant_role})` : ''}</p>}
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
                <div className="min-w-0"><p className="truncate text-xs font-medium">{source?.publisher || source?.title || item.source_id}</p><p className="break-all text-[11px] text-muted">{item.evidence_id} · {item.provenance.locator_type}</p></div>
                <button onClick={() => onInspectSource(item.source_id)} className="inline-flex shrink-0 items-center gap-1 rounded px-2 py-1 text-xs font-medium text-primary hover:bg-primary-soft"><FileSearch size={14} />Inspect source</button>
              </div>
              <details className="mt-3 text-xs"><summary className="cursor-pointer font-medium text-primary">Show exact provenance</summary><div className="mt-2 space-y-1 break-all text-muted"><p>{item.provenance.source_path}</p><p>{item.provenance.locator}</p>{item.provenance.original_text && <blockquote className="mt-2 border-l-2 border-line pl-3 text-ink">{item.provenance.original_text}</blockquote>}</div></details>
            </article>
          })}</div>}
        </section>
        {incident.unresolved_questions.length > 0 && <section><h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Unresolved questions</h3><ul className="list-disc space-y-2 pl-5 text-sm">{incident.unresolved_questions.map((item) => <li key={item}>{item}</li>)}</ul></section>}
      </div>
      <footer className="border-t border-line px-6 py-3 text-xs text-muted"><ExternalLink size={13} className="mr-1 inline" />This tool fuses attributed evidence; it does not establish truth or fault.</footer>
      {reviewOpen && <DetailedIncidentReview incident={incident} evidence={evidence} evidenceError={evidenceError} onClose={() => setReviewOpen(false)} onInspectSource={onInspectSource} />}
    </aside>
  )
}

function Data({ label, value }: { label: string; value: string }) {
  return <div className="rounded border border-line bg-canvas p-3"><p className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</p><p className="mt-1 text-sm font-semibold capitalize">{value}</p></div>
}

function casualtySummary(incident: Incident) {
  const values = incident.facts.filter((item) => item.field === 'fatalities' || item.field === 'injuries').map((item) => {
    const label = item.field === 'fatalities' ? 'fatalities' : 'injuries'
    if (item.state === 'reported_zero') return `0 ${label} explicitly reported`
    if (item.conflicting_values.length) return `${formatCasualtyFact(item)} ${label}`
    if (item.state !== 'known') return `${label} ${item.state.replaceAll('_', ' ')}`
    return `${formatCasualtyFact(item)} ${label}`
  })
  return values.join(' and ') || 'Casualty information not reported'
}
