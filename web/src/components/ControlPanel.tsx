import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { AccountRow, ControlState, ProviderConfig, Role, RunEstimate, RunSpec, RunState, Session } from '../types'

const ALL_ROLES: Role[] = ['admin', 'reviewer', 'annotator']
const PROVIDER_LABEL: Record<string, string> = { openai: 'ChatGPT (OpenAI)', anthropic: 'Claude (Anthropic)', openrouter: 'OpenRouter', deepseek: 'DeepSeek' }
const RUN_PROVIDERS = ['deepseek', 'openrouter']
const numOrNull = (value: string): number | null => (value.trim() === '' ? null : Number(value))

export function ControlPanel({ session }: { session: Session }) {
  const [state, setState] = useState<ControlState | null>(null)
  const [accounts, setAccounts] = useState<AccountRow[]>([])
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [newUser, setNewUser] = useState({ username: '', password: '', roles: ['annotator'] as Role[] })
  const [runs, setRuns] = useState<RunState[]>([])
  const [spec, setSpec] = useState<RunSpec>({ provider: 'deepseek', model: '', input_set: 'markdown', with_images: false, limit: null })
  const [estimate, setEstimate] = useState<RunEstimate | null>(null)
  const [pricingText, setPricingText] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const csrf = session.csrf_token

  const load = useCallback(async () => {
    try { setState(await api.control()); setAccounts(await api.accounts()) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Failed to load') }
  }, [])
  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const tick = () => api.runs().then(setRuns).catch(() => undefined)
    void tick()
    const timer = window.setInterval(tick, 3000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => { if (state) setPricingText(JSON.stringify(state.settings.pricing, null, 2)) }, [state?.settings.pricing]) // eslint-disable-line react-hooks/exhaustive-deps
  const run = async (action: () => Promise<unknown>, done: string) => {
    setError(''); setMessage('')
    try { await action(); setMessage(done); await load() } catch (cause) { setError(cause instanceof Error ? cause.message : 'Request failed') }
  }
  if (!state) return <p className="p-6 text-muted">{error || 'Loading…'}</p>
  const { settings } = state
  const patchProvider = (name: string, patch: Partial<ProviderConfig>) =>
    setState({ ...state, settings: { ...settings, providers: { ...settings.providers, [name]: { ...settings.providers[name], ...patch } } } })

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 p-4">
      {error && <p role="alert" className="border border-danger-line bg-danger-soft p-2 text-danger">{error}</p>}
      {message && <p className="border border-line bg-primary-soft p-2 text-primary" aria-live="polite">{message}</p>}

      <section className="panel p-4">
        <h2 className="mb-2 text-sm font-bold uppercase tracking-[0.18em] text-primary">Provider keys</h2>
        <p className="mb-3 text-muted">Keys are held in server memory only. They are never written to disk, logged, or shown again, and are lost when the server restarts (an environment variable such as OPENAI_API_KEY also works).</p>
        <div className="grid gap-2 md:grid-cols-2">{Object.keys(PROVIDER_LABEL).map((name) => (
          <div key={name} className="flex flex-col gap-1 border border-line p-2">
            <span className="label">{PROVIDER_LABEL[name]} · {state.keys[name]?.configured ? `set (${state.keys[name].source})` : 'not set'}</span>
            <div className="flex gap-1">
              <input className="control min-w-0 flex-1" type="password" autoComplete="off" placeholder="paste API key" value={keys[name] ?? ''} onChange={(event) => setKeys({ ...keys, [name]: event.target.value })} />
              <button className="btn" disabled={!keys[name]} onClick={() => void run(async () => { await api.setKey(name, keys[name], csrf); setKeys({ ...keys, [name]: '' }) }, `${PROVIDER_LABEL[name]} key set`)}>Set</button>
              <button className="btn" onClick={() => void run(() => api.setKey(name, null, csrf), `${PROVIDER_LABEL[name]} key cleared`)}>Clear</button>
            </div>
          </div>))}
        </div>
      </section>

      <section className="panel p-4">
        <h2 className="mb-2 text-sm font-bold uppercase tracking-[0.18em] text-primary">Models, pricing and limits</h2>
        <p className="mb-3 text-muted">A live call needs a model, both prices, and limits. There are no defaults, and a failed call is never retried on another provider.</p>
        <div className="grid gap-3 md:grid-cols-2">{Object.keys(PROVIDER_LABEL).map((name) => {
          const config = settings.providers[name]
          return (
            <fieldset key={name} className="flex flex-col gap-1 border border-line p-2"><legend className="label px-1">{PROVIDER_LABEL[name]}</legend>
              <input className="control" placeholder="model id" value={config.model} onChange={(event) => patchProvider(name, { model: event.target.value })} />
              <input className="control" placeholder="base URL (optional)" value={config.base_url} onChange={(event) => patchProvider(name, { base_url: event.target.value })} />
              <div className="grid grid-cols-2 gap-1">
                <input className="control" inputMode="decimal" placeholder="$ / 1M input tokens" value={config.input_cost_per_million_usd ?? ''} onChange={(event) => patchProvider(name, { input_cost_per_million_usd: numOrNull(event.target.value) })} />
                <input className="control" inputMode="decimal" placeholder="$ / 1M output tokens" value={config.output_cost_per_million_usd ?? ''} onChange={(event) => patchProvider(name, { output_cost_per_million_usd: numOrNull(event.target.value) })} />
              </div>
              <label className="flex items-center gap-2"><input type="checkbox" checked={config.supports_images} onChange={(event) => patchProvider(name, { supports_images: event.target.checked })} />model accepts images</label>
            </fieldset>)
        })}</div>
        <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
          {([['run_token_limit', 'Run token limit'], ['max_images_per_article', 'Max images / article'], ['run_cost_limit_usd', 'Run cost limit ($, if priced)'], ['concurrency', 'Concurrency']] as const).map(([field, label]) => (
            <label key={field} className="flex flex-col gap-1"><span className="label">{label}</span>
              <input className="control" inputMode="decimal" value={settings[field]} onChange={(event) => setState({ ...state, settings: { ...settings, [field]: Number(event.target.value) } })} /></label>))}
        </div>
        <label className="mt-3 flex items-center gap-2"><input type="checkbox" checked={settings.labelling_open} onChange={(event) => setState({ ...state, settings: { ...settings, labelling_open: event.target.checked } })} />
          Labelling is open (hides LLM output from anyone who also has the annotator role)</label>
        <button className="btn btn-primary mt-3" onClick={() => void run(() => api.saveControl(settings, csrf), 'Settings saved')}>Save settings</button>
      </section>

      <section className="panel p-4">
        <h2 className="mb-2 text-sm font-bold uppercase tracking-[0.18em] text-primary">Run extraction</h2>
        <p className="mb-3 text-muted">Runs resume: articles already extracted for the same provider, model and input are skipped. Cost may be unknown; token limits always apply. A failed call stays failed (no other provider is tried).</p>
        <div className="grid gap-2 md:grid-cols-4">
          <label className="flex flex-col gap-1"><span className="label">Provider</span>
            <select className="control" value={spec.provider} onChange={(event) => { setSpec({ ...spec, provider: event.target.value, model: settings.providers[event.target.value]?.model ?? '' }); setEstimate(null) }}>{RUN_PROVIDERS.map((name) => <option key={name} value={name}>{PROVIDER_LABEL[name]}</option>)}</select></label>
          <label className="flex flex-col gap-1 md:col-span-2"><span className="label">Model id (e.g. deepseek-flash, or an OpenRouter id ending :free)</span>
            <input className="control" value={spec.model} onChange={(event) => { setSpec({ ...spec, model: event.target.value }); setEstimate(null) }} /></label>
          <label className="flex flex-col gap-1"><span className="label">Input</span>
            <select className="control" value={spec.input_set} onChange={(event) => { setSpec({ ...spec, input_set: event.target.value as RunSpec['input_set'] }); setEstimate(null) }}><option value="markdown">markdown</option><option value="raw">raw HTML</option></select></label>
        </div>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <label className="flex items-center gap-2"><input type="checkbox" checked={spec.with_images} onChange={(event) => { setSpec({ ...spec, with_images: event.target.checked }); setEstimate(null) }} />include images (provider must be marked as image-capable above)</label>
          <label className="flex flex-col gap-1"><span className="label">Limit articles</span>
            <input className="control w-28" inputMode="numeric" placeholder="all" value={spec.limit ?? ''} onChange={(event) => { setSpec({ ...spec, limit: numOrNull(event.target.value) }); setEstimate(null) }} /></label>
          <button className="btn" disabled={!spec.model} onClick={() => void run(async () => setEstimate(await api.estimateRun(spec, csrf)), 'Estimate ready')}>Estimate</button>
          <button className="btn btn-primary" disabled={!spec.model || !estimate} onClick={() => void run(() => api.startRun(spec, csrf), 'Run started')}>Start run</button>
        </div>
        {estimate && <p className="mt-2 border border-line p-2">{estimate.articles_todo} of {estimate.articles_total} articles to do · ~{estimate.est_input_tokens.toLocaleString()} input + ~{estimate.est_output_tokens.toLocaleString()} output tokens · {estimate.images_to_send} images · cost: {estimate.est_cost_usd === null ? 'unknown (no price set)' : `$${estimate.est_cost_usd.toFixed(4)}`}{!estimate.within_token_limit && <span className="text-danger"> · exceeds the {estimate.token_limit.toLocaleString()}-token limit; the run will stop early</span>}</p>}
        <table className="mt-3 w-full border-collapse text-left"><thead><tr className="label"><th className="py-1">Configuration</th><th>Status</th><th>Done / failed</th><th>Tokens in/out</th><th>Cost</th><th /></tr></thead>
          <tbody>{runs.map((item) => (<tr key={item.config_id} className="border-t border-line"><td className="py-1 break-all">{item.config_id}</td>
            <td>{item.status}{item.stop_reason ? ` (${item.stop_reason})` : ''}</td><td>{item.done} / {item.failed}</td>
            <td>{item.input_tokens.toLocaleString()} / {item.output_tokens.toLocaleString()}</td><td>{item.cost_usd === null ? 'unknown' : `$${item.cost_usd}`}</td>
            <td>{item.status === 'running' && <button className="btn" onClick={() => void run(() => api.cancelRun(item.config_id, csrf), 'Cancel requested')}>Cancel</button>}</td></tr>))}</tbody></table>
      </section>

      <section className="panel p-4">
        <h2 className="mb-2 text-sm font-bold uppercase tracking-[0.18em] text-primary">Pricing (optional)</h2>
        <p className="mb-2 text-muted">Paste JSON keyed "provider/model" with USD per million tokens. Models without a price run with unknown cost; OpenRouter ids ending :free count as $0.</p>
        <textarea className="control w-full" rows={5} spellCheck={false} value={pricingText} onChange={(event) => setPricingText(event.target.value)} />
        <button className="btn mt-2" onClick={() => void run(async () => { await api.savePricing(JSON.parse(pricingText || '{}') as ControlState['settings']['pricing'], csrf) }, 'Pricing saved')}>Import pricing</button>
      </section>

      <section className="panel p-4">
        <h2 className="mb-2 text-sm font-bold uppercase tracking-[0.18em] text-primary">Accounts</h2>
        <table className="w-full border-collapse text-left"><thead><tr className="label"><th className="py-1">User</th><th>Roles</th><th>Status</th><th /></tr></thead>
          <tbody>{accounts.map((account) => (
            <tr key={account.username} className="border-t border-line"><td className="py-1">{account.username}</td>
              <td><div className="flex gap-2">{ALL_ROLES.map((role) => (
                <label key={role} className="flex items-center gap-1"><input type="checkbox" checked={account.roles.includes(role)} onChange={(event) => {
                  const roles = event.target.checked ? [...account.roles, role] : account.roles.filter((item) => item !== role)
                  if (roles.length) void run(() => api.saveAccount(account.username, roles, undefined, undefined, csrf), `${account.username} updated`)
                }} />{role}</label>))}</div></td>
              <td>{account.disabled ? 'disabled' : 'active'}</td>
              <td><button className="btn" onClick={() => void run(() => api.saveAccount(account.username, account.roles, undefined, !account.disabled, csrf), `${account.username} ${account.disabled ? 'enabled' : 'disabled'}`)}>{account.disabled ? 'Enable' : 'Disable'}</button></td></tr>))}</tbody></table>
        <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); void run(async () => { await api.saveAccount(newUser.username, newUser.roles, newUser.password, undefined, csrf); setNewUser({ username: '', password: '', roles: ['annotator'] }) }, 'Account saved') }}>
          <label className="flex flex-col gap-1"><span className="label">New / reset user</span><input className="control" placeholder="username" value={newUser.username} onChange={(event) => setNewUser({ ...newUser, username: event.target.value })} required /></label>
          <label className="flex flex-col gap-1"><span className="label">Password (12+)</span><input className="control" type="password" autoComplete="new-password" minLength={12} value={newUser.password} onChange={(event) => setNewUser({ ...newUser, password: event.target.value })} required /></label>
          {ALL_ROLES.map((role) => (<label key={role} className="flex items-center gap-1"><input type="checkbox" checked={newUser.roles.includes(role)} onChange={(event) => setNewUser({ ...newUser, roles: event.target.checked ? [...newUser.roles, role] : newUser.roles.filter((item) => item !== role) })} />{role}</label>))}
          <button className="btn btn-primary" disabled={!newUser.roles.length}>Save account</button>
        </form>
      </section>
    </div>
  )
}
