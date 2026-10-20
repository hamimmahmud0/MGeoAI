import { useCallback, useEffect, useMemo, useState } from 'react'
import { LogOut, Moon, Monitor, Sun } from 'lucide-react'
import { api } from './lib/api'
import type { Role, Session } from './types'
import { Annotate } from './components/Annotate'
import { ControlPanel } from './components/ControlPanel'
import { SignIn } from './components/SignIn'

type Theme = 'system' | 'light' | 'dark'
type Tab = 'annotate' | 'control'
const THEME_KEY = 'mgeoai-theme'

const TABS: { id: Tab; label: string; roles: Role[] }[] = [
  { id: 'annotate', label: 'Annotate', roles: ['annotator'] },
  { id: 'control', label: 'Control panel', roles: ['admin'] },
]

function readTheme(): Theme {
  try {
    const value = localStorage.getItem(THEME_KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch { return 'system' }
}

function useTheme() {
  const [theme, setTheme] = useState<Theme>(readTheme)
  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    const apply = () => {
      const resolved = theme === 'system' ? (media?.matches ? 'dark' : 'light') : theme
      document.documentElement.dataset.theme = resolved
      document.documentElement.style.colorScheme = resolved
    }
    apply()
    media?.addEventListener?.('change', apply)
    try { localStorage.setItem(THEME_KEY, theme) } catch { /* storage unavailable */ }
    return () => media?.removeEventListener?.('change', apply)
  }, [theme])
  return [theme, setTheme] as const
}

export function App() {
  const [theme, setTheme] = useTheme()
  const [session, setSession] = useState<Session | null>(null)
  const [checking, setChecking] = useState(true)
  const [tab, setTab] = useState<Tab | null>(null)

  useEffect(() => {
    api.me().then(setSession).catch(() => setSession(null)).finally(() => setChecking(false))
  }, [])

  const visible = useMemo(() => TABS.filter((item) => session?.roles.some((role) => item.roles.includes(role))), [session])
  const active = tab && visible.some((item) => item.id === tab) ? tab : visible[0]?.id
  const signOut = useCallback(async () => {
    if (session) await api.logout(session.csrf_token).catch(() => undefined)
    setSession(null)
  }, [session])
  const nextTheme = () => setTheme(theme === 'system' ? 'light' : theme === 'light' ? 'dark' : 'system')
  const ThemeIcon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-4 border-b border-line bg-surface px-4">
        <div className="py-2 text-[13px] font-bold tracking-[0.2em] text-primary">MGEOAI<span className="text-muted">/</span><span className="text-ink">EXTRACT</span></div>
        <nav role="tablist" aria-label="Sections" className="flex flex-1 overflow-x-auto">
          {visible.map((item) => (
            <button key={item.id} role="tab" aria-selected={active === item.id} className="tab" onClick={() => setTab(item.id)}>{item.label}</button>
          ))}
        </nav>
        <button className="btn" onClick={nextTheme} aria-label={`Theme: ${theme}`} title={`Theme: ${theme}`}><ThemeIcon size={14} />{theme}</button>
        {session && <button className="btn" onClick={signOut}><LogOut size={14} />{session.username}</button>}
      </header>
      <main className="flex-1">
        {checking ? <p className="p-6 text-muted">Checking session…</p>
          : !session ? <SignIn onSession={setSession} />
          : active === 'annotate' ? <Annotate session={session} />
          : active === 'control' ? <ControlPanel session={session} />
          : <p className="p-6 text-muted">This account has no available sections. Ask an admin for a role.</p>}
      </main>
    </div>
  )
}
