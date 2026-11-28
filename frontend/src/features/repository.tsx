import { ArrowRight, Database, FileCode2, GitBranch, GitFork, Network, Plus, RefreshCw, Search, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Snapshot } from '../api/contracts'
import { uuidPattern, validRepository } from '../api/validation'
import { Busy, Empty, ErrorNotice, Heading, Prepare } from '../ui'
import { hosted } from './auth'

const historyKey = 'repobrain.recent-snapshots'
type Saved = Pick<Snapshot, 'snapshot_id' | 'repository' | 'commit_sha'>
function savedSnapshots(): Saved[] {
  if (hosted) return []
  try {
    const data: unknown = JSON.parse(localStorage.getItem(historyKey) ?? '[]')
    if (!Array.isArray(data)) return []
    return data.filter((item): item is Saved => !!item && typeof item === 'object'
      && typeof item.snapshot_id === 'string' && uuidPattern.test(item.snapshot_id)
      && typeof item.repository === 'string' && validRepository(item.repository)
      && typeof item.commit_sha === 'string' && /^[0-9a-f]{40}$/.test(item.commit_sha)).slice(0, 12)
  } catch { return [] }
}
export function remember(snapshot: Snapshot) {
  if (hosted) return
  try {
    const { snapshot_id, repository, commit_sha } = snapshot
    const list = savedSnapshots().filter((item) => item.snapshot_id !== snapshot_id)
    localStorage.setItem(historyKey, JSON.stringify([{ snapshot_id, repository, commit_sha }, ...list].slice(0, 12)))
  } catch { /* optional browser history */ }
}
export function useSnapshot(id: string) {
  const [deadline, setDeadline] = useState(() => Date.now() + 5 * 60_000)
  const client = useQueryClient()
  const result = useQuery({
    queryKey: ['snapshot', id, 'ingestion'], queryFn: ({ signal }) => api.snapshot(id, signal),
    enabled: uuidPattern.test(id),
    refetchInterval: ({ state }) => Date.now() < deadline &&
      (state.data?.state === 'pending' || state.data?.state === 'running') ? 2500 : false,
  })
  const snapshot = result.data
  useEffect(() => {
    if (!snapshot) return
    remember(snapshot)
    if (snapshot.state === 'completed') {
      void client.invalidateQueries({ queryKey: ['snapshot', id, 'readiness'] })
      void client.invalidateQueries({ queryKey: ['snapshot', id, 'summary'] })
    }
  }, [snapshot, id, client])
  return { ...result, refresh: () => { setDeadline(Date.now() + 5 * 60_000); void result.refetch() } }
}

export function RepositoryPage({ id, snapshot }: { id?: string; snapshot?: Snapshot }) {
  const [repo, setRepo] = useState('')
  const [ref, setRef] = useState('')
  const [open, setOpen] = useState('')
  const [formError, setFormError] = useState('')
  const [openError, setOpenError] = useState('')
  const [recent, setRecent] = useState(savedSnapshots)
  const navigate = useNavigate()
  const client = useQueryClient()
  const ingest = useMutation({
    mutationFn: ({ repository, reference }: { repository: string; reference?: string }) => api.ingest(repository, reference),
    onSuccess: (data) => {
      remember(data)
      setRecent(savedSnapshots())
      client.setQueryData(['snapshot', data.snapshot_id, 'ingestion'], data)
      navigate('/snapshots/' + data.snapshot_id + '/repository')
    },
  })
  function submit(event: FormEvent) {
    event.preventDefault()
    if (ingest.isPending) return
    if (!validRepository(repo.trim())) { setFormError('Use a public repository in owner/name format.'); return }
    setFormError('')
    ingest.mutate({ repository: repo.trim(), reference: ref.trim() || undefined })
  }
  return <div className="page-stack"><Heading eyebrow="Workspace" title="Repositories">Import a public Python repository or reopen a pinned snapshot.</Heading>
    <div className="columns">
      <section className="panel"><div className="panel-title"><Plus size={17} /><h2>Import repository</h2></div>
        <form onSubmit={submit} className="pad stack">
          <label className="field">GitHub repository<input placeholder="owner/repository" value={repo} maxLength={140} onChange={(e) => setRepo(e.target.value)} required /></label>
          <label className="field">Branch, tag or commit <span className="muted">(optional)</span><input placeholder="Default branch" maxLength={200} value={ref} onChange={(e) => setRef(e.target.value)} /></label>
          {formError && <p role="alert" className="error-text">{formError}</p>}
          {ingest.isError && <ErrorNotice error={ingest.error} />}
          <button className="primary self-start" disabled={ingest.isPending}>{ingest.isPending ? 'Starting ingestion…' : 'Start ingestion'} <ArrowRight size={16} /></button>
        </form>
      </section>
      <section className="panel"><div className="panel-title"><Database size={17} /><h2>Open snapshot</h2></div>
        <form className="pad stack" onSubmit={(event) => {
          event.preventDefault()
          if (!uuidPattern.test(open.trim())) { setOpenError('Enter a snapshot UUID.'); return }
          setOpenError('')
          navigate('/snapshots/' + open.trim().toLowerCase() + '/overview')
        }}>
          <label className="field">Snapshot UUID<input className="mono" value={open} onChange={(e) => setOpen(e.target.value)} required placeholder="Paste a snapshot UUID" /></label>
          {openError && <p className="error-text" role="alert">{openError}</p>}
          <button className="self-start">Open snapshot <ArrowRight size={16} /></button>
        </form>
      </section>
    </div>
    {snapshot && <section className="panel"><div className="panel-title"><GitFork size={17} /><h2>Active ingestion</h2><span className={'badge ' + snapshot.state}>{snapshot.state}</span></div>
      <div className="pad"><p>{snapshot.file_count} stored files · <code>{snapshot.snapshot_id}</code></p>
      {snapshot.error && <p role="alert" className="error-text">{snapshot.error.message}</p>}</div>
    </section>}
    <section className="panel"><div className="panel-title"><GitBranch size={17} /><h2>Recent snapshots</h2></div>
      {recent.length ? <ul className="list">{recent.map((item) => <li key={item.snapshot_id}><Link to={'/snapshots/' + item.snapshot_id + '/overview'}><strong>{item.repository}</strong><code>{item.commit_sha.slice(0, 12)}</code><ArrowRight size={16} /></Link></li>)}</ul>
        : <Empty>Snapshots opened on this browser appear here.</Empty>}
    </section>
    {!hosted && id && snapshot?.state === 'completed' && <Prepare id={id} />}
  </div>
}

export function Overview({ snapshot }: { snapshot: Snapshot }) {
  const id = snapshot.snapshot_id
  const ready = useQuery({ queryKey: ['snapshot', id, 'readiness'], queryFn: ({ signal }) => api.readiness(id, signal), enabled: snapshot.state === 'completed' })
  const graph = useQuery({ queryKey: ['snapshot', id, 'summary'], queryFn: ({ signal }) => api.summary(id, signal), enabled: ready.data?.graph_analyzed === true })
  const metrics = [
    { title: 'Stored source files', value: snapshot.file_count, icon: FileCode2 },
    { title: 'Analyzed files', value: graph.data?.analyzed_files, icon: CodeFile },
    { title: 'Graph nodes', value: graph.data?.node_count, icon: Network },
    { title: 'Directed edges', value: graph.data?.edge_count, icon: GitFork },
  ]
  return <div className="page-stack"><Heading eyebrow="Snapshot overview" title={snapshot.repository}>Explore the indexed source and dependency relationships for this immutable commit.</Heading>
    <div className="metrics">{metrics.map(({ title, value, icon: Icon }) => <div className="metric" key={title}><div><Icon size={17} />{title}</div><strong>{value === undefined ? '—' : value.toLocaleString()}</strong></div>)}</div>
    <div className="columns">
      <section className="panel"><div className="panel-title"><Database size={17} /><h2>Snapshot readiness</h2><button type="button" className="quiet" disabled={snapshot.state !== 'completed'} onClick={() => { void ready.refetch(); if (graph.data) void graph.refetch() }}><RefreshCw size={15} /> Refresh</button></div>
        <dl className="readiness"><div><dt>Ingestion</dt><dd className={'badge ' + snapshot.state}>{snapshot.state}</dd></div>
          <div><dt>Graph analysis</dt><dd>{ready.data ? (ready.data.graph_analyzed ? 'Ready' : 'Required') : '—'}</dd></div>
          <div><dt>Lexical index</dt><dd>{ready.data ? (ready.data.lexical_version ?? 'Required') : '—'}</dd></div>
          <div><dt>Vector index</dt><dd>{hosted ? 'Unavailable' : ready.data ? (ready.data.vector_version ?? 'Required') : '—'}</dd></div>
        </dl>
        {ready.isFetching && <Busy>Checking snapshot readiness</Busy>}
        {ready.isError && <ErrorNotice error={ready.error} />}
        {graph.isError && <ErrorNotice error={graph.error} />}
        {graph.data && <div className="pad sub-divider"><p>{graph.data.diagnostic_count} graph diagnostics</p><div className="pills">{graph.data.supported_relationships.map((item) => <code key={item}>{item}</code>)}</div></div>}
      </section>
      <section className="panel"><div className="panel-title"><GitBranch size={17} /><h2>Snapshot identity</h2></div>
        <dl className="identity pad"><dt>Commit SHA</dt><dd><code>{snapshot.commit_sha}</code></dd><dt>Snapshot UUID</dt><dd><code>{id}</code></dd></dl>
        <div className="list shortcuts">
          <Link to={'/snapshots/' + id + '/search'}><Search size={17} />Search source<ArrowRight size={15} /></Link>
          <Link to={'/snapshots/' + id + '/graph'}><Network size={17} />Explore dependencies<ArrowRight size={15} /></Link>
          <Link to={'/snapshots/' + id + '/answers'}><Sparkles size={17} />Ask a question<ArrowRight size={15} /></Link>
        </div>
      </section>
    </div>
    {!hosted && ready.data && (!ready.data.graph_analyzed || !ready.data.lexical_version || !ready.data.vector_version) && <Prepare id={id} />}
    {hosted && ready.data && (!ready.data.graph_analyzed || !ready.data.lexical_version) &&
      <p className="notice">{ready.data.managed_preparation
        ? 'Graph and lexical preparation may still be running. Refresh readiness to check.'
        : 'Automatic index preparation is disabled. Contact the operator about snapshot readiness.'}</p>}
  </div>
}
const CodeFile = FileCode2
