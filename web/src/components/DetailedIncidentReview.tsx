import { AlertTriangle, CalendarClock, FileSearch, MapPin, Route, ShieldQuestion, Users, X } from 'lucide-react'
import type { Incident, IncidentEvidence } from '../types'

type Props = {
  incident: Incident
  evidence?: IncidentEvidence
  evidenceError: string
  onClose: () => void
  onInspectSource: (id: string) => void
}

export function DetailedIncidentReview({ incident, evidence, evidenceError, onClose, onInspectSource }: Props) {
  const evidenceBySource = evidence ? Object.entries(evidence.sources).map(([sourceId, source]) => {
    const items = evidence.items.filter((item) => item.source_id === sourceId)
    return {
      sourceId,
      source,
      count: items.length,
      modalities: [...new Set(items.map((item) => item.modality))],
      assertions: [...new Set(items.map((item) => item.assertion_type.replaceAll('_', ' ')))],
    }
  }).sort((left, right) => right.count - left.count) : []

  return <div className="fixed inset-0 z-40 bg-black/45 p-0 sm:p-5">
    <button className="absolute inset-0 cursor-default" onClick={onClose} aria-label="Close detailed fused review" />
    <section className="relative mx-auto flex h-full w-full max-w-5xl flex-col overflow-hidden border border-line bg-surface shadow-2xl sm:rounded-lg" role="dialog" aria-modal="true" aria-labelledby="fused-review-title">
      <header className="flex items-start justify-between gap-5 border-b border-line px-5 py-4 sm:px-7 sm:py-5">
        <div><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-primary">Detailed fused review</p><h2 id="fused-review-title" className="text-xl font-semibold leading-snug sm:text-2xl">{incident.title}</h2><p className="mt-2 text-xs text-muted">Generated {formatDateTime(incident.generated_at)} · {incident.status} record</p></div>
        <button onClick={onClose} className="shrink-0 rounded p-2 text-muted hover:bg-canvas" aria-label="Close detailed fused review panel"><X size={20} /></button>
      </header>

      <div className="flex-1 space-y-8 overflow-y-auto px-5 py-6 sm:px-7">
        <section className="rounded border border-primary/30 bg-primary-soft p-5">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-primary">Executive fused assessment</h3>
          <p className="text-sm leading-7 sm:text-base">{incident.human_summary}</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <ReviewDatum icon={<CalendarClock size={16} />} label="Reported time" value={formatInterval(incident)} detail={`${incident.event_time.precision} precision`} />
            <ReviewDatum icon={<MapPin size={16} />} label="Reported location" value={incident.geolocation.display_name || 'Unresolved'} detail={`${Math.round(incident.geolocation.confidence * 100)}% location confidence`} />
            <ReviewDatum icon={<Users size={16} />} label="Independent groups" value={String(incident.independent_source_count)} detail={`${incident.source_ids.length} source record(s)`} />
            <ReviewDatum icon={<ShieldQuestion size={16} />} label="Open questions" value={String(incident.unresolved_questions.length)} detail={`${incident.evidence_ids.length} evidence item(s)`} />
          </div>
        </section>

        <section>
          <SectionHeading title="Fact-by-fact assessment" description="Selected values, confidence, conflicts, and the evidence basis retained by fusion." />
          <div className="grid gap-3 md:grid-cols-2">{incident.facts.map((fact) => <article key={fact.field} className="rounded border border-line bg-canvas p-4">
            <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-muted">{labelize(fact.field)}</p><p className="mt-1 text-lg font-semibold">{factValue(fact.value, fact.state)}</p></div><span className="badge">{Math.round(fact.confidence * 100)}% confidence</span></div>
            <p className="mt-3 text-xs leading-5 text-muted">{fact.selection_rationale}</p>
            <p className="mt-2 text-xs text-muted">Supported by {fact.support_evidence_ids.length} cited evidence item(s).</p>
            {fact.conflicting_values.length > 0 && <div className="mt-3 rounded border border-warning-line bg-warning-soft p-3 text-xs text-warning"><b>Conflicting alternatives:</b> {fact.conflicting_values.map(String).join(', ')}</div>}
          </article>)}</div>
        </section>

        <section>
          <SectionHeading title="Event and traffic review" description="Structured incident details are shown as reported; missing fields are not inferred." />
          <div className="grid gap-3 md:grid-cols-2">
            <ReviewList icon={<Route size={17} />} label="Collision description" items={incident.collision ? [incident.collision] : []} />
            <ReviewList icon={<Users size={17} />} label="Vehicles and parties" items={[...incident.vehicles, ...incident.involved_parties]} />
            <ReviewList icon={<Route size={17} />} label="Traffic and obstruction" items={[incident.congestion_delay, incident.obstruction].filter((item): item is string => Boolean(item))} />
            <ReviewList icon={<ShieldQuestion size={17} />} label="Emergency response" items={incident.emergency_response} />
            <ReviewList icon={<AlertTriangle size={17} />} label="Attributed contributing factors" items={incident.contributing_factors} />
            <ReviewList icon={<CalendarClock size={17} />} label="Later developments" items={incident.later_developments} />
          </div>
        </section>

        <section>
          <SectionHeading title="Location and time certainty" description="Coordinates and dates preserve the granularity and ambiguity of the supplied evidence." />
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded border border-line p-4"><p className="text-sm font-semibold">{incident.geolocation.display_name || 'Location unresolved'}</p><p className="mt-2 text-xs leading-5 text-muted">Method: {labelize(incident.geolocation.method)} · {labelize(incident.geolocation.granularity)} granularity{incident.geolocation.uncertainty_radius_km ? ` · approximately ${incident.geolocation.uncertainty_radius_km} km uncertainty radius` : ''}</p>{incident.geolocation.ambiguity_reason && <p className="mt-3 text-sm leading-6">{incident.geolocation.ambiguity_reason}</p>}{incident.geolocation.alternatives.length > 0 && <p className="mt-3 text-xs text-warning">Alternative locations: {incident.geolocation.alternatives.map((item) => `${item.name} (${Math.round(item.confidence * 100)}%)`).join(', ')}</p>}</div>
            <div className="rounded border border-line p-4"><p className="text-sm font-semibold">{formatInterval(incident)}</p><p className="mt-2 text-xs leading-5 text-muted">{labelize(incident.event_time.precision)} precision{incident.event_time.timezone ? ` · ${incident.event_time.timezone}` : ' · timezone not supplied'}</p>{incident.event_time.original_expression && <p className="mt-3 text-sm leading-6">Normalized from: {incident.event_time.original_expression}</p>}{incident.alternate_time_claims.length > 0 && <p className="mt-3 text-xs text-warning">{incident.alternate_time_claims.length} alternate time claim(s) retained.</p>}</div>
          </div>
        </section>

        <section>
          <SectionHeading title="Source and evidence coverage" description="Copies and syndicated reports do not count as additional independent corroboration." />
          {!evidence && !evidenceError && <p className="text-sm text-primary">Loading evidence coverage…</p>}
          {evidenceError && <p role="alert" className="text-sm text-danger">Evidence coverage could not be loaded: {evidenceError}</p>}
          {evidence && <div className="overflow-x-auto rounded border border-line"><table className="w-full min-w-[680px] text-left text-sm"><thead className="border-b border-line bg-canvas text-[11px] uppercase tracking-wide text-muted"><tr><th className="px-4 py-3">Source</th><th className="px-4 py-3">Evidence</th><th className="px-4 py-3">Modalities</th><th className="px-4 py-3">Assertion types</th><th className="px-4 py-3"><span className="sr-only">Action</span></th></tr></thead><tbody>{evidenceBySource.map((row) => <tr key={row.sourceId} className="border-b border-line last:border-0"><td className="px-4 py-3"><p className="font-medium">{row.source.publisher || row.source.title || 'Unknown source'}</p><p className="mt-1 max-w-xs truncate text-xs text-muted">{row.source.title || row.sourceId}</p></td><td className="px-4 py-3 tabular-nums">{row.count}</td><td className="px-4 py-3 capitalize">{row.modalities.join(', ')}</td><td className="px-4 py-3 capitalize">{row.assertions.join(', ')}</td><td className="px-4 py-3"><button onClick={() => onInspectSource(row.sourceId)} className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-primary hover:bg-primary-soft"><FileSearch size={14} />Inspect</button></td></tr>)}</tbody></table></div>}
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <div><SectionHeading title="Unresolved questions" />{incident.unresolved_questions.length ? <ul className="list-disc space-y-2 pl-5 text-sm leading-6">{incident.unresolved_questions.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="text-sm text-muted">No unresolved questions were recorded.</p>}</div>
          <div><SectionHeading title="Data-quality notices" />{incident.data_quality_warnings.length ? <ul className="list-disc space-y-2 pl-5 text-sm leading-6">{incident.data_quality_warnings.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="text-sm text-muted">No additional data-quality warnings were recorded.</p>}</div>
        </section>

        <section><SectionHeading title="Sentiment coverage" /><p className="text-sm leading-6">{incident.sentiment.coverage_note}</p>{Object.keys(incident.sentiment.by_aspect).length > 0 && <div className="mt-3 flex flex-wrap gap-2">{Object.entries(incident.sentiment.by_aspect).map(([aspect, values]) => <span className="badge" key={aspect}>{labelize(aspect)}: {Object.entries(values).map(([key, value]) => `${key} ${value}`).join(' · ')}</span>)}</div>}</section>
      </div>

      <footer className="border-t border-line px-5 py-3 text-xs text-muted sm:px-7">This review summarizes attributed evidence and fusion decisions. It does not independently verify the event or establish fault.</footer>
    </section>
  </div>
}

function SectionHeading({ title, description }: { title: string; description?: string }) {
  return <div className="mb-3"><h3 className="text-xs font-semibold uppercase tracking-wider text-muted">{title}</h3>{description && <p className="mt-1 text-xs leading-5 text-muted">{description}</p>}</div>
}

function ReviewDatum({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string; detail: string }) {
  return <div className="rounded border border-primary/20 bg-surface p-3"><div className="flex items-center gap-2 text-primary">{icon}<p className="text-[11px] font-semibold uppercase tracking-wide">{label}</p></div><p className="mt-2 text-sm font-semibold">{value}</p><p className="mt-1 text-[11px] text-muted">{detail}</p></div>
}

function ReviewList({ icon, label, items }: { icon: React.ReactNode; label: string; items: string[] }) {
  return <div className="rounded border border-line bg-canvas p-4"><div className="flex items-center gap-2 text-primary">{icon}<p className="text-xs font-semibold uppercase tracking-wide">{label}</p></div>{items.length ? <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm leading-6">{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="mt-3 text-sm text-muted">Not reported in the fused record.</p>}</div>
}

function labelize(value: string) { return value.replaceAll('_', ' ') }
function factValue(value: unknown, state: string) {
  if (state === 'reported_zero') return '0 (explicitly reported)'
  if (state !== 'known') return labelize(state)
  if (Array.isArray(value)) return value.join(', ')
  return String(value ?? 'Unknown')
}
function formatDateTime(value: string) { return new Date(value).toLocaleString() }
function formatInterval(incident: Incident) {
  const { start, end } = incident.event_time
  if (!start) return 'Not reported'
  const startLabel = new Date(start).toLocaleDateString()
  if (!end || new Date(end).toLocaleDateString() === startLabel) return startLabel
  return `${startLabel} – ${new Date(end).toLocaleDateString()}`
}
