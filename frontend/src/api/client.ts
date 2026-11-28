import type {
  Answer, Direction, GraphSummary, Mode, Neighborhood, NodeKind, NodePage,
  Readiness, Relationship, SearchResponse, Snapshot, SourceWindow,
} from './contracts'

const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
let accessToken: string | undefined
let expireSession: () => void = () => undefined
export function setApiSession(token?: string, onExpired: () => void = () => undefined) {
  accessToken = token
  expireSession = onExpired
}
const messages: Record<number, string> = {
  404: 'The requested snapshot or source could not be found.',
  409: 'This snapshot needs preparation. Check its graph and index status.',
  422: 'Check the submitted values and try again.',
  429: 'The service is busy. Try again after the current requests finish.',
  502: 'An upstream service returned an invalid response.',
  503: 'A required service is unavailable.',
  504: 'The request timed out.',
}
const actions: Record<string, string> = {
  generation_unavailable: 'Set the generation endpoint and model in the backend environment. Search and graph exploration are still available.',
  embedding_unavailable: 'Configure the pinned embedding model on the backend before using this retrieval mode.',
  vector_index_unavailable: 'Build the vector index for this snapshot from the repository workspace.',
  search_index_unavailable: 'Build the lexical index for this snapshot from the repository workspace.',
  graph_analysis_unavailable: 'Analyze this snapshot with the graph CLI from the repository workspace.',
}
export class ApiError extends Error {
  constructor(public status: number, public code: string, public requestId: string | null, message: string) {
    super(message)
  }
}

function errorFields(body: unknown) {
  if (!body || typeof body !== 'object' || !('error' in body)) return {}
  const error = body.error
  if (!error || typeof error !== 'object') return {}
  return {
    code: 'code' in error && typeof error.code === 'string' ? error.code : undefined,
    message: 'message' in error && typeof error.message === 'string' ? error.message : undefined,
    id: 'request_id' in error && typeof error.request_id === 'string' ? error.request_id : undefined,
  }
}

async function request<T>(path: string, signal?: AbortSignal, payload?: object, method = payload ? 'POST' : 'GET'): Promise<T> {
  let response: Response
  const token = accessToken
  try {
    response = await fetch(base + '/api/v1' + path, {
      signal,
      headers: { Accept: 'application/json', ...(payload ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: 'Bearer ' + token } : {}) },
      method, body: payload ? JSON.stringify(payload) : undefined,
      redirect: 'error',
    })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError(0, 'network_error', null, 'The backend could not be reached. Check that it is running.')
  }
  if (response.status === 204) return undefined as T
  let body: unknown
  try {
    body = await response.json()
  } catch (error) {
    if (signal?.aborted) throw error
  }
  if (!response.ok) {
    if (response.status === 401 && token && accessToken === token) expireSession()
    const { code, message, id } = errorFields(body)
    throw new ApiError(response.status, code ?? 'http_error', id ?? response.headers.get('X-Request-ID'),
      (code && Object.hasOwn(actions, code) ? actions[code] : message) || messages[response.status] || 'The request failed.')
  }
  if (!body || typeof body !== 'object') {
    throw new ApiError(502, 'invalid_response', response.headers.get('X-Request-ID'), 'The backend returned an invalid response.')
  }
  return body as T
}

const scope = (id: string) => '/snapshots/' + encodeURIComponent(id)
const withQuery = (path: string, entries: [string, string | number | null | undefined][]) => {
  const query = new URLSearchParams()
  for (const [key, value] of entries) if (value !== null && value !== undefined && value !== '') query.append(key, String(value))
  return path + '?' + query.toString()
}

export const api = {
  provision: () => request<Workspace>('/workspace', undefined, undefined, 'POST'),
  workspace: (signal?: AbortSignal) => request<Workspace>('/workspace', signal),
  removeRepository: (id: string) => request<void>('/workspace/repositories/' + encodeURIComponent(id), undefined, undefined, 'DELETE'),
  removeWorkspace: () => request<void>('/workspace', undefined, undefined, 'DELETE'),
  removeAccount: () => request<void>('/workspace/account', undefined, undefined, 'DELETE'),
  ingest: (repository: string, ref?: string) => request<Snapshot>('/repositories/ingestions', undefined, { repository, ref }),
  snapshot: (id: string, signal?: AbortSignal) => request<Snapshot>('/ingestions/' + encodeURIComponent(id), signal),
  readiness: (id: string, signal?: AbortSignal) => request<Readiness>(scope(id) + '/readiness', signal),
  summary: (id: string, signal?: AbortSignal) => request<GraphSummary>(scope(id) + '/graph', signal),
  nodes: (id: string, filter: { kind: NodeKind | ''; name: string; path: string; cursor: string | null }, signal?: AbortSignal) =>
    request<NodePage>(withQuery(scope(id) + '/nodes', [
      ['limit', 24], ['kind', filter.kind], ['qualified_name_prefix', filter.name], ['path', filter.path], ['cursor', filter.cursor],
    ]), signal),
  neighborhood: (id: string, node: string, direction: Direction, depth: 1 | 2, relationships: Relationship[], signal?: AbortSignal) =>
    request<Neighborhood>(withQuery(scope(id) + '/neighborhood', [
      ['node_id', node], ['direction', direction], ['depth', depth], ...relationships.map((value): [string, Relationship] => ['relationship', value]),
    ]), signal),
  source: (id: string, path: string, start: number | null, end: number | null, signal?: AbortSignal) =>
    request<SourceWindow>(withQuery(scope(id) + '/source', [['path', path], ['start_line', start], ['end_line', end]]), signal),
  search: (id: string, mode: Mode, q: string, limit: number, signal?: AbortSignal) =>
    request<SearchResponse>(withQuery(scope(id) + '/search/' + mode, [['q', q], ['limit', limit]]), signal),
  answer: (id: string, question: string, mode: Mode, signal?: AbortSignal) =>
    request<Answer>(scope(id) + '/answer', signal, { question, retrieval_mode: mode }),
}

export interface Workspace {
  id: string
  snapshots: { id: string; repository: string; commit_sha: string; snapshot_id: string }[]
}
