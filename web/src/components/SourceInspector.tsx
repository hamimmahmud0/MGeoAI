import { ExternalLink, FileText, X } from 'lucide-react'
import type { SourceDetail } from '../types'

export function SourceInspector({ source, onClose }: { source: SourceDetail; onClose: () => void }) {
  return (
    <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[640px] flex-col border-l border-line bg-surface shadow-xl" aria-label="Source content" aria-live="polite">
      <header className="flex items-start justify-between border-b border-line px-6 py-5">
        <div className="min-w-0 pr-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-primary">Source record</p>
          <h2 className="text-xl font-semibold leading-snug">{source.title || source.publisher || 'Untitled source'}</h2>
          <p className="mt-2 break-all text-xs text-muted">{source.source_id}</p>
        </div>
        <button onClick={onClose} className="rounded p-2 text-muted hover:bg-canvas" aria-label="Close source content"><X size={19} /></button>
      </header>
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <section className="grid grid-cols-2 gap-3">
          <Data label="Publisher" value={source.publisher || 'Unknown'} />
          <Data label="Platform" value={source.platform || 'Local file'} />
          <Data label="Type" value={source.source_type.replaceAll('_', ' ')} />
          <Data label="Independence" value={source.dependency_group || source.independence} />
        </section>

        <div className="my-5 flex flex-wrap gap-2">
          {source.source_uri && <a className="inline-flex items-center gap-2 rounded border border-line bg-surface px-3 py-2 text-sm font-medium text-primary hover:bg-canvas" href={source.source_uri} target="_blank" rel="noreferrer"><ExternalLink size={15} />Open original source</a>}
          <span className="inline-flex items-center gap-2 rounded border border-line bg-canvas px-3 py-2 text-xs text-muted"><FileText size={14} />{source.blocks.length} extracted content block(s)</span>
        </div>

        <section>
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Extracted source content</h3>
          {source.blocks.length ? <div className="space-y-3">{source.blocks.map((block) => (
            <article key={block.block_id} className="rounded border border-line bg-surface p-4">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span className="badge">{block.kind}</span>
                <span className="break-all text-[11px] text-muted">{block.block_id}</span>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-6">{block.text}</p>
              {(block.author || block.reactions !== undefined) && <p className="mt-3 text-xs text-muted">{block.author ? `By ${block.author}` : ''}{block.author && block.reactions !== undefined ? ' · ' : ''}{block.reactions !== undefined ? `${block.reactions} reactions` : ''}</p>}
            </article>
          ))}</div> : <pre className="whitespace-pre-wrap rounded border border-line bg-canvas p-4 font-sans text-sm leading-6">{source.content || 'No readable content was extracted for this source.'}</pre>}
        </section>

        <section className="mt-7">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Evidence extracted from this source</h3>
          {source.evidence.length ? <div className="space-y-3">{source.evidence.map((item) => (
            <article key={item.evidence_id} className="rounded border border-line bg-canvas p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2"><span className="badge">{item.assertion_type.replaceAll('_', ' ')}</span><span className="badge">{item.modality}</span><span className="ml-auto text-[11px] text-muted">{Math.round(item.extraction_confidence * 100)}% confidence</span></div>
              <p className="text-sm leading-6">{item.claim_text}</p>
              <details className="mt-3 text-xs"><summary className="cursor-pointer font-medium text-primary">Show evidence ID and locator</summary><div className="mt-2 space-y-1 break-all text-muted"><p>{item.evidence_id}</p><p>{item.provenance.source_path}</p><p>{item.provenance.locator}</p></div></details>
            </article>
          ))}</div> : <p className="text-sm text-muted">No evidence claims were extracted from this source.</p>}
        </section>
      </div>
      <footer className="border-t border-line px-6 py-3 text-xs text-muted">Content is a safe extracted representation. Embedded source scripts and markup are never executed.</footer>
    </aside>
  )
}

function Data({ label, value }: { label: string; value: string }) {
  return <div className="rounded border border-line bg-canvas p-3"><p className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</p><p className="mt-1 text-sm font-semibold capitalize">{value}</p></div>
}
