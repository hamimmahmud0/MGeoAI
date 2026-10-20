import { useState } from 'react'
import { api } from '../lib/api'
import type { Session } from '../types'

export function SignIn({ onSession }: { onSession: (session: Session) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true); setError('')
    try { onSession(await api.login(username.trim(), password)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Sign-in failed') }
    finally { setBusy(false) }
  }
  return (
    <form onSubmit={submit} className="panel mx-auto mt-16 flex w-full max-w-sm flex-col gap-3 p-5">
      <h1 className="text-sm font-bold uppercase tracking-[0.2em] text-primary">Sign in</h1>
      <label className="flex flex-col gap-1"><span className="label">Username</span>
        <input className="control" value={username} autoComplete="username" onChange={(event) => setUsername(event.target.value)} required /></label>
      <label className="flex flex-col gap-1"><span className="label">Password</span>
        <input className="control" type="password" value={password} autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} required /></label>
      {error && <p role="alert" className="border border-danger-line bg-danger-soft p-2 text-danger">{error}</p>}
      <button className="btn btn-primary justify-center" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
    </form>
  )
}
