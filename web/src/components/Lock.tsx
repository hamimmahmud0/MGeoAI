import { Lock as LockIcon } from 'lucide-react'

export function LockNotice({ what }: { what: string }) {
  return (
    <div role="status" className="panel m-4 flex items-start gap-3 p-4">
      <LockIcon size={16} className="mt-0.5 text-warning" />
      <p><span className="label block">{what} locked</span>Hidden while labelling is open, so annotators stay independent of model output and of each other. It appears here as soon as an admin ends labelling.</p>
    </div>
  )
}

export function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="panel p-3"><div className="label">{label}</div><div className="mt-1 text-xl font-bold text-primary">{value}</div>{hint && <div className="text-muted">{hint}</div>}</div>
  )
}
