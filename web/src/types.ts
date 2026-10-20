export type Role = 'admin' | 'reviewer' | 'annotator'
export type Session = { username: string; roles: Role[]; disabled: boolean; csrf_token: string }

export const VEHICLES = [
  'car', 'bus', 'truck', 'covered_van', 'pickup', 'microbus', 'motorcycle', 'cng_autorickshaw',
  'battery_autorickshaw', 'rickshaw', 'human_hauler', 'bicycle', 'tractor', 'train', 'ambulance', 'van',
] as const

export type AccidentRecord = {
  accident: boolean
  casualities: number | null
  fatalities: number | null
  vehicles: string[] | null
  date: string | null
  country: string | null
  location: string | null
  'longitude and latitude': string | null
  evidences: { field: string; quote: string; note?: string | null }[]
}
export type ImageLabel = { image_id: string; description: string; shows_accident: boolean | null; vehicles_visible: string[]; notes: string }
export type ArticleImage = { image_id: string; url: string; alt: string }
export type ArticleRow = { id: string; title: string | null; publisher: string | null; done: boolean }
export type ArticleQueue = { annotator: string; total: number; labeled: number; articles: ArticleRow[] }
export type MyLabel = { accidents: AccidentRecord[]; images: ImageLabel[]; unusable: boolean; notes: string; revision: number }
export type ArticleDetail = {
  id: string; url: string | null; publisher: string | null; title: string | null; published_at: string | null; language: string | null
  markdown: string; images: ArticleImage[]; my_label: MyLabel | null
}
export type AccountRow = { username: string; roles: Role[]; disabled: boolean }
export type ProviderConfig = {
  model: string; base_url: string; input_cost_per_million_usd: number | null; output_cost_per_million_usd: number | null
  timeout_seconds: number; max_output_tokens: number; supports_images: boolean; thinking?: 'disabled' | 'default'
}
export type ControlSettings = {
  labelling_open: boolean; pricing: Record<string, { input_per_million_usd: number; output_per_million_usd: number }>
  run_token_limit: number; max_images_per_article: number; run_cost_limit_usd: number; daily_cost_limit_usd: number; concurrency: number
  providers: Record<string, ProviderConfig>
}
export type KeyStatus = Record<string, { configured: boolean; source: 'ui_memory' | 'environment' | 'none' }>
export type ControlState = { settings: ControlSettings; keys: KeyStatus }

export const emptyAccident = (): AccidentRecord => ({
  accident: true, casualities: null, fatalities: null, vehicles: [], date: null, country: null,
  location: null, 'longitude and latitude': null, evidences: [],
})

export type RunSpec = { provider: string; model: string; input_set: 'raw' | 'markdown'; with_images: boolean; limit?: number | null; only_failed?: boolean }
export type RunEstimate = {
  config_id: string; articles_total: number; articles_todo: number; images_to_send: number
  est_input_tokens: number; est_output_tokens: number; est_cost_usd: number | null; cost_known: boolean
  token_limit: number; within_token_limit: boolean; note: string
}
export type RunState = {
  config_id: string; status: 'running' | 'finished' | 'stopped' | 'cancelled' | 'interrupted'; started_at: string; finished_at: string | null
  done: number; failed: number; input_tokens: number; output_tokens: number; cost_usd: number | null; cost_known: boolean
  stop_reason: string | null; spec: RunSpec; attempt?: { done: number; failed: number; input_tokens: number; output_tokens: number }
}

export type Overview = {
  labelling_open: boolean; articles: number; images: number; articles_with_images: number
  top_publishers: [string, number][]; languages: [string, number][]
  labelling: { annotators: number; articles_with_1plus_labels: number; articles_with_3plus_labels: number; labels_submitted: number }
}
export type Locked = { locked: true; message: string }
export type MapProps = {
  incident_id?: string; title?: string; publisher?: string; source_url?: string; origin?: string; verified?: boolean
  fatalities?: number | null; casualities?: number | null; date?: string | null; location?: string | null; country?: string | null
  granularity?: string; uncertainty_radius_km?: number; is_incident_location?: boolean; location_method?: string
  articles?: number; note?: string; location_name?: string
}
export type MapFeature = Omit<GeoJSON.Feature<GeoJSON.Point>, 'properties'> & { properties: MapProps }
export type MapCollection = { type: 'FeatureCollection'; features: MapFeature[] }
export type MapData = MapCollection & { locked?: false; meta?: { source: string; records: number; mapped: number; verified: boolean } }
export type AnnotationScores = {
  locked: false; articles_total: number; annotators: Record<string, number>; articles_with_1plus_labels: number
  articles_with_2plus_labels: number; articles_with_3plus_labels: number; accident_flag_alpha: number | null
  accident_flag_cohen_kappa: Record<string, { kappa: number | null; articles: number }>
  field_exact_agreement: Record<string, { agree: number; pairs: number; rate: number | null }>
  gold_articles: number; gold_unresolved_flag: number; min_labels_for_gold: number
}
type Rate = { n: number; value: number | null; ci95: number[] | null }
export type ModelRow = {
  config_id: string; spec: RunSpec; tokens: { input: number; output: number }; cost_usd: number | null; cost_known: boolean
  metrics: {
    articles_ok: number; articles_failed: number; scored_articles: number
    accident_flag: { precision: number | null; recall: number | null; f1: number | null; tp: number; fp: number; fn: number; tn: number }
    accident_count_correct: Rate; fields_exact: Record<string, Rate>; fatalities_mae: number | null; vehicles_jaccard: number | null
    location_token_overlap: number | null; evidence_quotes_verbatim: { quotes: number; verbatim: number; rate: number | null }
    mean_latency_ms: number | null; note: string
  }
}
