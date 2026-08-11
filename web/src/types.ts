export type Fact = { field: string; value: unknown; state: string; confidence: number; conflicting_values: unknown[]; support_evidence_ids: string[]; contradiction: boolean; selection_rationale: string }
export type SentimentItem = { sentiment_id: string; holder: string; target: string; aspect: string; polarity: string; emotion?: string; evidence_id: string; confidence: number }
export type TimeInterval = { start?: string; end?: string; original_expression?: string; timezone?: string; precision: string }
export type LocationAlternative = { name: string; normalized_name: string; granularity: string; confidence: number; reason?: string }
export type Incident = {
  incident_id: string; title: string; event_type: string; status: string; severity: string; mapped: boolean;
  event_time: TimeInterval; alternate_time_claims: TimeInterval[];
  geolocation: { display_name?: string; latitude?: number; longitude?: number; granularity: string; confidence: number; ambiguity_reason?: string; uncertainty_radius_km?: number; alternatives: LocationAlternative[]; hierarchy: Record<string, string>; method: string; supporting_evidence_ids: string[] };
  facts: Fact[]; involved_parties: string[]; vehicles: string[]; collision?: string; obstruction?: string; congestion_delay?: string; emergency_response: string[]; contributing_factors: string[]; later_developments: string[]; source_ids: string[]; evidence_ids: string[];
  independent_source_count: number; duplicate_groups: string[][];
  sentiment: { items: SentimentItem[]; by_aspect: Record<string, Record<string, number>>; sample_size: number; traffic_relevant_count: number; coverage_note: string; notable_minority_views: string[] };
  unresolved_questions: string[]; data_quality_warnings: string[]; human_summary: string; generated_at: string; provider_run_id?: string;
}
export type Source = { source_id: string; source_type: string; publisher?: string; platform?: string; title?: string; local_path: string; independence: string; dependency_group?: string; ingest_warnings: string[]; linked_incident_ids: string[] }
export type Provenance = { source_path: string; locator_type: string; locator: string; block_id?: string; original_text?: string }
export type SourceBlock = { block_id: string; source_id: string; kind: string; text: string; author?: string; url?: string; reactions?: number; locator: Provenance }
export type SourceDetail = Source & { source_uri?: string; author?: string; published_at?: string; languages: string[]; content: string; blocks: SourceBlock[]; evidence: Evidence[] }
export type Evidence = {
  evidence_id: string; source_id: string; modality: string; evidence_kind: string; assertion_type: string;
  claim_text: string; claimant?: string; claimant_role?: string; extraction_confidence: number;
  location_mentions: string[]; time_mentions: string[]; traffic_effects: string[]; warnings: string[];
  source_support?: string; provenance: Provenance;
}
export type IncidentEvidence = { items: Evidence[]; sources: Record<string, Source> }
export type ProviderRun = { run_id: string; cluster_id: string; operation: string; provider: string; model: string; finish_status: string; latency_ms: number; input_tokens?: number; output_tokens?: number; retries: number; validation_status: string; prompt_hash: string; error?: string }
export type Page<T> = { items: T[]; total: number; page: number; page_size: number }
export type SubmissionStatus = 'pending' | 'processing' | 'approved' | 'rejected' | 'ingest_failed'
export type SubmissionAudit = { action: string; actor: string; at: string; detail?: string }
export type Submission = {
  submission_id: string; status: SubmissionStatus; source_kind: 'news' | 'social' | 'other';
  title: string; publisher?: string; source_uri?: string; content: string; submitter_name?: string;
  submitted_at: string; reviewed_by?: string; reviewed_at?: string; review_note?: string;
  pipeline_run_id?: string; loaded_source_ids: string[]; loaded_incident_ids: string[];
  ingest_error?: string; audit: SubmissionAudit[];
}
export type SubmissionInput = Pick<Submission, 'source_kind' | 'title' | 'content'> & { publisher?: string; source_uri?: string; submitter_name?: string }
export type ReviewerSession = { username: string; csrf_token: string }
