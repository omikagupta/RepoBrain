import { lazy, Suspense, useState } from 'react'
import { Activity, ArrowRight, BookOpen, GitBranch, GitFork, LayoutDashboard, Moon, Network, Search, Sparkles, Sun } from 'lucide-react'
import { Link, Navigate, NavLink, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { uuidPattern } from './api/validation'
import type { Snapshot } from './api/contracts'
import { Overview, RepositoryPage, useSnapshot } from './features/repository'
import { SearchPage, AnswerPage } from './features/retrieval'
import { Busy, Empty, ErrorNotice, Heading } from './ui'

const GraphPage = lazy(() => import('./features/graph').then(({ GraphPage }) => ({ default: GraphPage })))

const items = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard },
  { key: 'repository', label: 'Repository workspace', icon: BookOpen },
  { key: 'search', label: 'Code search', icon: Search },
  { key: 'answers', label: 'AI answers', icon: Sparkles },
  { key: 'graph', label: 'Dependency graph', icon: Network },
]

function Shell({ snapshot, id, children }: { snapshot?: Snapshot; id?: string; children: React.ReactNode }) {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('repobrain.theme') === 'light' ? 'light' : 'dark' } catch { return 'dark' }
  })
  const location = useLocation()
  const section = items.find((item) => location.pathname.endsWith('/' + item.key))?.label ?? (location.pathname === '/repositories' ? 'Repository workspace' : 'Overview')
  return <div className="shell" data-theme={theme}>
    <a href="#workspace-main" className="skip">Skip to content</a>
    <aside className="sidebar">
      <Link to={id ? '/snapshots/' + id + '/overview' : '/'} className="brand"><span className="brand-mark"><Network size={22} /></span><span><strong>RepoBrain</strong><small>Code intelligence</small></span></Link>
      <div className="nav-section">WORKSPACE</div>
      <nav aria-label="Workspace">
        {items.map(({ key, label, icon: Icon }) => {
          const destination = id ? '/snapshots/' + id + '/' + key : key === 'repository' ? '/repositories' : key === 'overview' ? '/' : ''
          return destination ? <NavLink key={key} to={destination} end><Icon size={17} /><span>{label}</span></NavLink>
            : <span key={key} className="disabled-nav" aria-disabled="true"><Icon size={17} /><span>{label}</span></span>
        })}
      </nav>
      <div className="sidebar-foot"><Link to="/repositories"><GitFork size={16} /> Switch snapshot</Link></div>
    </aside>
    <div className="work-area">
      <header className="topbar"><div className="breadcrumb"><GitFork size={16} /><span>{snapshot?.repository ?? 'Workspace'}</span><span className="separator">/</span><strong>{section}</strong></div>
        <div className="row top-actions">{snapshot && <span className="commit-pill" title={snapshot.commit_sha}><GitBranch size={14} /><code>{snapshot.commit_sha.slice(0, 12)}</code></span>}
          <button className="icon-btn" aria-label={theme === 'dark' ? 'Use light theme' : 'Use dark theme'} type="button" onClick={() => {
            const next = theme === 'dark' ? 'light' : 'dark'
            setTheme(next)
            try { localStorage.setItem('repobrain.theme', next) } catch { /* preference is optional */ }
          }}>{theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}</button></div>
      </header>
      <main id="workspace-main" className="main">{children}</main>
    </div>
  </div>
}

function SnapshotRoute() {
  const { snapshotId = '', page = '' } = useParams()
  const snapshot = useSnapshot(snapshotId)
  const record = snapshot.data
  if (!uuidPattern.test(snapshotId)) return <Shell><Empty>This snapshot link has an invalid UUID.</Empty></Shell>
  if (!items.some((item) => item.key === page)) return <Navigate replace to={'/snapshots/' + snapshotId + '/overview'} />
  return <Shell snapshot={record} id={snapshotId}>
    {snapshot.isError && <ErrorNotice error={snapshot.error} />}
    {snapshot.isPending && <Busy>Loading snapshot</Busy>}
    {record && (record.state === 'pending' || record.state === 'running') && <div className="notice polling"><Activity size={16} /> Ingestion is {record.state}. <button className="quiet" onClick={snapshot.refresh}>Refresh status</button></div>}
    {page === 'repository' && <RepositoryPage key={snapshotId} id={snapshotId} snapshot={record} />}
    {record && page === 'overview' && <Overview key={snapshotId} snapshot={record} />}
    {record && !['overview', 'repository'].includes(page) && (record.state !== 'completed'
      ? <Empty>Ingestion must complete before opening this workspace.</Empty>
      : page === 'search' ? <SearchPage key={snapshotId} id={snapshotId} /> : page === 'answers'
        ? <AnswerPage key={snapshotId} id={snapshotId} /> : <Suspense fallback={<Busy>Loading dependency explorer</Busy>}><GraphPage key={snapshotId} id={snapshotId} /></Suspense>)}
  </Shell>
}
function Home() {
  return <Shell><div className="page-stack"><Heading eyebrow="Repository intelligence" title="Explore a pinned codebase">Open a snapshot to search source, trace dependencies, and ask evidence-grounded questions.</Heading><section className="panel welcome"><Network size={36} /><h2>Choose a repository</h2><p>Import a public Python repository or reopen an existing snapshot by UUID.</p><Link className="button primary" to="/repositories">Open repository workspace <ArrowRight size={16} /></Link></section></div></Shell>
}
export function App() {
  return <Routes><Route path="/" element={<Home />} /><Route path="/repositories" element={<Shell><RepositoryPage /></Shell>} />
    <Route path="/snapshots/:snapshotId" element={<SnapshotRoute />} />
    <Route path="/snapshots/:snapshotId/:page" element={<SnapshotRoute />} />
    <Route path="*" element={<Navigate to="/" replace />} /></Routes>
}
