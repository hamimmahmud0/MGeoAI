import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import type { Incident, IncidentEvidence } from '../types'
import { DetailedIncidentReview } from './DetailedIncidentReview'

afterEach(cleanup)

const incident: Incident = {
  incident_id: 'inc_test', title: 'Reported road crash', event_type: 'road_crash', status: 'reported', severity: 'high', mapped: true,
  event_time: { start: '2026-08-10T00:00:00Z', precision: 'day', original_expression: '10 August' }, alternate_time_claims: [],
  geolocation: { display_name: 'Test Road', latitude: 23.8, longitude: 90.4, granularity: 'area', confidence: 0.8, uncertainty_radius_km: 3, ambiguity_reason: 'Exact point unknown.', alternatives: [], hierarchy: { country: 'Bangladesh' }, method: 'gazetteer', supporting_evidence_ids: ['ev_test'] },
  facts: [{ field: 'fatalities', value: 1, state: 'known', confidence: 0.8, conflicting_values: [], support_evidence_ids: ['ev_test'], contradiction: false, selection_rationale: 'Selected from explicit reports.' }],
  involved_parties: [], vehicles: ['bus'], collision: 'Bus and motorcycle collision', emergency_response: [], contributing_factors: [], later_developments: [],
  source_ids: ['src_test'], evidence_ids: ['ev_test'], independent_source_count: 1, duplicate_groups: [],
  sentiment: { items: [], by_aspect: {}, sample_size: 0, traffic_relevant_count: 0, coverage_note: 'No sentiment supplied.', notable_minority_views: [] },
  unresolved_questions: ['Exact point remains unknown.'], data_quality_warnings: [], human_summary: 'A detailed attributed summary of the reported collision and its material facts.', generated_at: '2026-08-11T00:00:00Z',
}

const evidence: IncidentEvidence = {
  items: [{ evidence_id: 'ev_test', source_id: 'src_test', modality: 'text', evidence_kind: 'article', assertion_type: 'reported', claim_text: 'One fatality was reported.', extraction_confidence: 0.9, location_mentions: ['Test Road'], time_mentions: ['10 August'], traffic_effects: [], warnings: [], provenance: { source_path: 'content.html', locator_type: 'html_selector', locator: 'p' } }],
  sources: { src_test: { source_id: 'src_test', source_type: 'news_html', publisher: 'Test News', title: 'Crash report', local_path: 'content.html', independence: 'original', ingest_warnings: [], linked_incident_ids: ['inc_test'] } },
}

test('shows the complete fused review and exposes its source', () => {
  const inspect = vi.fn()
  render(<DetailedIncidentReview incident={incident} evidence={evidence} evidenceError="" onClose={vi.fn()} onInspectSource={inspect} />)
  expect(screen.getByRole('dialog', { name: 'Reported road crash' })).toBeInTheDocument()
  expect(screen.getByText('Fact-by-fact assessment')).toBeInTheDocument()
  expect(screen.getByText('Source and evidence coverage')).toBeInTheDocument()
  expect(screen.getByText('Selected from explicit reports.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Inspect' }))
  expect(inspect).toHaveBeenCalledWith('src_test')
})
