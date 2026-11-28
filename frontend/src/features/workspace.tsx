import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { Busy, ErrorNotice, Heading } from '../ui'
import { signOut } from './auth'

export function WorkspacePage() {
  const client = useQueryClient()
  const workspace = useQuery({ queryKey: ['workspace'], queryFn: ({ signal }) => api.workspace(signal) })
  const change = useMutation({
    mutationFn: async (action: { type: 'create' | 'workspace' | 'account' } | { type: 'repo'; id: string }) => {
      switch (action.type) {
        case 'create': await api.provision(); break
        case 'repo': await api.removeRepository(action.id); break
        case 'workspace': await api.removeWorkspace(); break
        case 'account': await api.removeAccount(); await signOut(); break
      }
    },
    onSuccess: async () => { await client.invalidateQueries() },
  })
  const logout = useMutation({ mutationFn: signOut })
  const missing = workspace.error instanceof ApiError && workspace.error.status === 404
  return <div className="page-stack">
    <Heading eyebrow="Account" title="Your workspace">Manage access to your pinned public repository snapshots.</Heading>
    <button className="button" disabled={logout.isPending} onClick={() => logout.mutate()}>Sign out</button>
    {workspace.isPending && <Busy>Loading workspace</Busy>}
    {workspace.isError && !missing && <ErrorNotice error={workspace.error} />}
    {(change.error || logout.error) && <ErrorNotice error={change.error ?? logout.error} />}
    {missing && <button className="button primary" disabled={change.isPending} onClick={() => change.mutate({ type: 'create' })}>Create workspace</button>}
    {workspace.data && <>
      <Link className="button primary" to="/repositories">Import a repository</Link>
      {workspace.data.snapshots.length === 0 && <p>No snapshots yet.</p>}
      <ul>{workspace.data.snapshots.map((item) => <li key={item.snapshot_id} className="row">
        <Link to={'/snapshots/' + item.snapshot_id + '/overview'}>{item.repository} <code>{item.commit_sha.slice(0, 12)}</code></Link>
        <button className="button" disabled={change.isPending} onClick={() => { if (window.confirm('Remove this repository and all its snapshots from your workspace?')) change.mutate({ type: 'repo', id: item.id }) }}>Remove repository</button>
      </li>)}</ul>
      <button className="button" disabled={change.isPending} onClick={() => { if (window.confirm('Remove your workspace and all its repository access?')) change.mutate({ type: 'workspace' }) }}>Delete workspace</button>
    </>}
    <p>Deleting your RepoBrain account revokes workspace access. Public source snapshots can be retained for other workspaces.</p>
    <button className="button" disabled={change.isPending} onClick={() => { if (window.confirm('Permanently close your RepoBrain account?')) change.mutate({ type: 'account' }) }}>Delete RepoBrain account</button>
  </div>
}
