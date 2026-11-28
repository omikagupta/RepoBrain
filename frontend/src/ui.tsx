import { AlertCircle, ArrowUpRight, BookOpen, ChevronRight, CircleHelp, Code2, GitBranch, LoaderCircle } from 'lucide-react'
import { useId, useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from './api/client'
import type { Identity, Mode, Policy, Provenance } from './api/contracts'
import { pinnedLink, sourceLines } from './api/validation'

export const modes: { id: Mode; title: string; description: string; score: string }[] = [
  { id: 'lexical', title: 'Lexical', description: 'Match exact names and tokens in indexed source.', score: 'Lexical score' },
  { id: 'vector', title: 'Vector', description: 'Find semantically related code using embeddings.', score: 'Cosine similarity' },
  { id: 'hybrid', title: 'Hybrid RRF', description: 'Fuse lexical and vector ranks without mixing raw scores.', score: 'RRF score' },
  { id: 'graph-enhanced', title: 'Graph-enhanced', description: 'Expand hybrid seeds through stored dependency edges.', score: 'Graph-enhanced score' },
]

export function ModeSelect({ mode, onChange }: { mode: Mode; onChange: (mode: Mode) => void }) {
  const selected = modes.find((item) => item.id === mode)!
  const hint = useId()
  return <div className="field grow"><label htmlFor={hint + '-select'}>Retrieval mode</label>
    <select id={hint + '-select'} aria-describedby={hint} value={mode} onChange={(event) => {
      const option = modes.find((item) => item.id === event.target.value)
      if (option) onChange(option.id)
    }}>{modes.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select>
    <small id={hint}>{selected.description}</small>
  </div>
}

export function ErrorNotice({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  return <div className="notice error" role="alert"><AlertCircle size={17} /><div>{message}
    {error instanceof ApiError && error.requestId && <small className="request-id">Request ID <code>{error.requestId}</code></small>}
  </div></div>
}

export function Busy({ children }: { children: ReactNode }) {
  return <div className="notice" role="status"><LoaderCircle size={17} className="spinner" />{children}</div>
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty"><CircleHelp size={20} /><div>{children}</div></div>
}

export function Heading({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return <header className="page-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{children}</p></header>
}

export function Policies({ policy }: { policy: Policy }) {
  return <div className="pills" aria-label="Policy versions">
    {[policy.chunking_version, policy.vector_version, policy.fusion?.version, policy.expansion?.version, policy.expansion?.ranking_version]
      .filter(Boolean).map((entry) => <code key={entry}>{entry}</code>)}
  </div>
}

export function GitHubLink({ identity, path, start, end, url }: { identity: Identity; path: string; start: number | null; end: number | null; url: string }) {
  const href = pinnedLink(identity, path, start, end, url)
  return href ? <a href={href} target="_blank" rel="noopener noreferrer" className="button quiet">GitHub <ArrowUpRight size={14} /></a> : null
}

export function CodeLines({ lines }: { lines: { line_number: number; text: string }[] }) {
  return <div className="code-scroll" tabIndex={0} aria-label="Source excerpt">
    <pre>{lines.map(({ line_number, text }) => <span className="code-line" key={line_number}><span aria-hidden="true" className="line-number">{line_number}</span><code>{text || ' '}</code></span>)}</pre>
  </div>
}

export function EvidencePanel({ evidence, start, end, path, url, text, lines, children }: {
  evidence: Identity; start: number | null; end: number | null; path: string; url: string; text?: string;
  lines?: { line_number: number; text: string }[]; children?: ReactNode
}) {
  const [copy, setCopy] = useState('')
  const numbered = lines ?? sourceLines(text ?? '').map((line, index) => ({ line_number: (start ?? 1) + index, text: line }))
  return <section className="panel evidence" aria-label="Evidence inspector">
    <div className="panel-title"><Code2 size={17} /><strong>{path}</strong>
      {start !== null && <code className="muted">L{start}{end !== start ? '–' + end : ''}</code>}
    </div>
    <div className="evidence-meta"><span className="muted">Pinned commit <code>{evidence.commit_sha}</code></span>
      <div className="row"><GitHubLink identity={evidence} path={path} start={start} end={end} url={url} />
      {numbered.length > 0 && <button className="quiet" type="button" onClick={async () => {
        try { await navigator.clipboard.writeText(text ?? numbered.map((line) => line.text).join('\n')); setCopy('Copied') }
        catch { setCopy('Clipboard unavailable') }
      }}>Copy source</button>}<span role="status">{copy}</span></div>
    </div>
    {numbered.length ? <CodeLines lines={numbered} /> : <Empty>This source window has no lines.</Empty>}
    {children}
  </section>
}

export function ProvenancePanel({ snapshot, provenance }: { snapshot: string; provenance: Provenance }) {
  const center = provenance.node_ids[0]
  const params = new URLSearchParams({ node: center ?? '', depth: String(Math.min(2, Math.max(1, provenance.hop_count))) })
  provenance.node_ids.forEach((id) => params.append('highlight-node', id))
  provenance.edges.forEach((edge) => params.append('highlight-edge', edge.edge_id))
  return <details className="provenance"><summary><GitBranch size={15} /> Graph provenance · {provenance.hop_count} {provenance.hop_count === 1 ? 'hop' : 'hops'}</summary>
    <p>Seed chunk <code>{provenance.seed_chunk_id}</code> · rank {provenance.seed_rank}</p>
    <ol>{provenance.edges.map((edge) => <li key={edge.edge_id}><code>{edge.source_node_id}</code> <strong>{edge.relationship} →</strong> <code>{edge.target_node_id}</code></li>)}</ol>
    {center && <Link to={'/snapshots/' + snapshot + '/graph?' + params.toString()} className="button quiet">Open neighborhood <ChevronRight size={14} /></Link>}
  </details>
}

export function Prepare({ id }: { id: string }) {
  return <section className="panel"><div className="panel-title"><BookOpen size={17} /><h2>Prepare this snapshot</h2></div>
    <div className="pad"><p>Run these commands from the repository root after ingestion completes. The vector build requires the pinned model assets and the vector Compose override.</p>
      <pre className="commands">{[
        '$snapshot = "' + id + '"',
        'docker compose run --rm --no-deps backend python -m repobrain.graph $snapshot',
        'docker compose run --rm --no-deps backend python -m repobrain.search $snapshot',
        'docker compose -f compose.yaml -f compose.vector.yaml run --rm --no-deps backend python -m repobrain.search.vector_cli $snapshot',
      ].join('\n')}</pre></div>
  </section>
}
