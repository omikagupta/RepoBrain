export type Mode = 'lexical' | 'vector' | 'hybrid' | 'graph-enhanced'
export type Relationship = 'CONTAINS' | 'IMPORTS' | 'IMPORTS_SYMBOL'
export type NodeKind = 'module' | 'class' | 'function' | 'method'
export type Direction = 'incoming' | 'outgoing' | 'both'

export interface Identity {
  snapshot_id: string
  repository: string
  commit_sha: string
}
export interface Snapshot extends Identity {
  state: 'pending' | 'running' | 'completed' | 'failed'
  file_count: number
  error: { code: string; message: string } | null
}
export interface Readiness extends Identity {
  graph_analyzed: boolean
  lexical_version: string | null
  vector_version: string | null
}
export interface GraphSummary extends Identity {
  analyzed_files: number
  node_count: number
  edge_count: number
  diagnostic_count: number
  supported_relationships: Relationship[]
}
export interface GraphNode {
  id: string
  snapshot_id: string
  kind: NodeKind
  qualified_name: string
  path: string
  start_line: number | null
  end_line: number | null
  is_async: boolean
}
export interface GraphEdge {
  id: string
  snapshot_id: string
  source_id: string
  target_id: string
  relationship: Relationship
  line: number | null
  column: number | null
  provenance: string
}
export interface NodePage { items: GraphNode[]; next_cursor: string | null }
export interface Neighborhood {
  snapshot_id: string
  center_node_id: string
  depth: 1 | 2
  nodes: GraphNode[]
  edges: GraphEdge[]
  truncated: boolean
}
export interface LineRange { start_line: number | null; end_line: number | null }
export interface SourceWindow extends Identity {
  path: string
  requested_range: LineRange
  actual_range: LineRange
  lines: { line_number: number; text: string }[]
  content_sha256: string
  permalink: string
}
export interface Provenance {
  seed_chunk_id: string
  seed_rank: number
  seed_score: number
  node_ids: string[]
  edges: {
    edge_id: string; source_node_id: string; target_node_id: string; relationship: Relationship
  }[]
  hop_count: number
}
export interface Evidence extends Identity {
  chunk_id: string
  source_file_id: string
  path: string
  start_line: number
  end_line: number
  text: string
  source_sha256: string
  content_sha256: string
  permalink: string
  score: number
  rank: number
}
export interface SearchHit extends Evidence {
  channels?: ('lexical' | 'vector' | 'graph')[]
  lexical_rank?: number | null
  lexical_score?: number | null
  vector_rank?: number | null
  vector_score?: number | null
  hybrid_rank?: number | null
  hybrid_score?: number | null
  graph_contribution?: number
  provenance?: Provenance | null
}
export interface Policy {
  chunking_version: string
  vector_version?: string | null
  fusion?: { version: string; k: number } | null
  expansion?: { version: string; ranking_version: string } | null
}
export interface SearchResponse extends Identity, Policy {
  query: string
  results: SearchHit[]
  traversal?: { truncated: boolean }
  metric?: string
}
export interface Citation extends Evidence {
  citation_id: string
  provenance: Provenance | null
}
export interface Answer extends Identity {
  question: string
  retrieval: Policy & { mode: Mode }
  generator: { model: string; provider: string } | null
  prompt_version: string
  status: 'answered' | 'insufficient_evidence'
  claims: { text: string; kind: 'observation' | 'inference'; citations: string[] }[]
  citations: Citation[]
  limitations: string[]
  citation_status: 'structurally_valid' | 'not_applicable'
  retrieved_count: number
  included_evidence_count: number
  context_truncated: boolean
  evidence_bytes: number
  retrieval_ms: number
  generation_ms: number | null
  total_ms: number
  usage: { input_tokens: number | null; output_tokens: number | null } | null
}
