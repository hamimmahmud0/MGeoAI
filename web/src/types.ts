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
  timeout_seconds: number; max_output_tokens: number; supports_images: boolean
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

export type RunSpec = { provider: string; model: string; input_set: 'raw' | 'markdown'; with_images: boolean; limit?: number | null }
export type RunEstimate = {
  config_id: string; articles_total: number; articles_todo: number; images_to_send: number
  est_input_tokens: number; est_output_tokens: number; est_cost_usd: number | null; cost_known: boolean
  token_limit: number; within_token_limit: boolean; note: string
}
export type RunState = {
  config_id: string; status: 'running' | 'finished' | 'stopped' | 'cancelled'; started_at: string; finished_at: string | null
  done: number; failed: number; input_tokens: number; output_tokens: number; cost_usd: number | null; cost_known: boolean
  stop_reason: string | null; spec: RunSpec
}
