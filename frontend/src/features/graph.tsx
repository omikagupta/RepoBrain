import cytoscape from 'cytoscape'
import type { Core, ElementDefinition } from 'cytoscape'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { Focus, Layers3, Minus, Network, Plus, RotateCcw, Search } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Direction, GraphEdge, GraphNode, NodeKind, Relationship } from '../api/contracts'
import { uuidPattern } from '../api/validation'
import { Busy, Empty, ErrorNotice, EvidencePanel, Heading } from '../ui'

const kinds: NodeKind[] = ['module', 'class', 'function', 'method']
const relationships: Relationship[] = ['CONTAINS', 'IMPORTS', 'IMPORTS_SYMBOL']
const palette = { module: '#3978bb', class: '#8657bf', function: '#187f73', method: '#a47126' }
const directions: Direction[] = ['both', 'incoming', 'outgoing']

function Canvas({ nodes, edges, center, nodeHighlights, edgeHighlights, onSelect }: {
  nodes: GraphNode[]; edges: GraphEdge[]; center: string; nodeHighlights: string[]; edgeHighlights: string[]; onSelect: (id: string) => void
}) {
  const host = useRef<HTMLDivElement>(null)
  const instance = useRef<Core | null>(null)
  const selection = useRef(onSelect)
  useEffect(() => { selection.current = onSelect }, [onSelect])
  const elements = useMemo<ElementDefinition[]>(() => [
    ...nodes.map((node) => ({ data: { id: node.id, label: node.qualified_name, color: palette[node.kind] },
      classes: (node.id === center ? 'center ' : '') + (nodeHighlights.includes(node.id) ? 'highlight' : '') })),
    ...edges.map((edge) => ({ data: { id: edge.id, source: edge.source_id, target: edge.target_id, label: edge.relationship },
      classes: edgeHighlights.includes(edge.id) ? 'highlight' : '' })),
  ], [nodes, edges, center, nodeHighlights, edgeHighlights])
  function layout() {
    instance.current?.layout({ name: 'breadthfirst', directed: true, padding: 48, spacingFactor: 1.4, animate: false }).run()
  }
  useEffect(() => {
    if (!host.current) return
    const cy = cytoscape({
      container: host.current, elements, minZoom: 0.15, maxZoom: 3,
      layout: { name: 'breadthfirst', directed: true, padding: 48, spacingFactor: 1.4, animate: false },
      style: [
        { selector: 'node', style: { label: 'data(label)', 'background-color': 'data(color)', shape: 'round-rectangle',
          width: 42, height: 34, 'font-size': 10, color: '#f6faff', 'text-outline-color': '#152438',
          'text-outline-width': 2, 'text-valign': 'bottom', 'text-margin-y': 7, 'text-wrap': 'wrap', 'text-max-width': '130px' } },
        { selector: 'edge', style: { width: 2, 'line-color': '#6987a2', 'target-arrow-color': '#6987a2',
          'target-arrow-shape': 'triangle', 'curve-style': 'bezier' } },
        { selector: 'node.center, node.highlight', style: { 'border-color': '#54dfd1', 'border-width': 3 } },
        { selector: 'edge.highlight', style: { 'line-color': '#54dfd1', 'target-arrow-color': '#54dfd1', width: 4 } },
      ],
    })
    instance.current = cy
    cy.on('tap', 'node', (event) => selection.current(event.target.id()))
    const resize = new ResizeObserver(() => cy.resize())
    resize.observe(host.current)
    return () => { resize.disconnect(); cy.destroy(); instance.current = null }
  }, [elements])
  return <><div className="canvas-tools" aria-label="Graph viewport controls">
    <button type="button" aria-label="Zoom in" onClick={() => { const cy = instance.current; if (cy) cy.zoom(cy.zoom() * 1.25) }}><Plus size={16} /></button>
    <button type="button" aria-label="Zoom out" onClick={() => { const cy = instance.current; if (cy) cy.zoom(cy.zoom() / 1.25) }}><Minus size={16} /></button>
    <button type="button" onClick={() => instance.current?.fit(undefined, 42)}><Focus size={16} /> Fit</button>
    <button type="button" onClick={layout}><RotateCcw size={15} /> Reset view</button>
  </div><div className="graph-canvas" ref={host} aria-hidden="true" /></>
}

const emptyNodes: GraphNode[] = []
const emptyEdges: GraphEdge[] = []
export function GraphPage({ id }: { id: string }) {
  const [params, setParams] = useSearchParams()
  const center = params.get('node') ?? ''
  const depth = params.get('depth') === '2' ? 2 : 1
  const highlights = useMemo(() => ({
    nodes: params.getAll('highlight-node').filter((item) => uuidPattern.test(item)).slice(0, 3),
    edges: params.getAll('highlight-edge').filter((item) => uuidPattern.test(item)).slice(0, 2),
  }), [params])
  const [direction, setDirection] = useState<Direction>('both')
  const [relationship, setRelationship] = useState<Relationship | ''>('')
  const [kind, setKind] = useState<NodeKind | ''>('')
  const [name, setName] = useState('')
  const [path, setPath] = useState('')
  const [filter, setFilter] = useState({ kind, name, path })
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const [inspect, setInspect] = useState(false)
  const cursor = cursors[cursors.length - 1]
  const ready = useQuery({ queryKey: ['snapshot', id, 'readiness'], queryFn: ({ signal }) => api.readiness(id, signal) })
  const nodes = useQuery({
    queryKey: ['snapshot', id, 'nodes', filter, cursor],
    queryFn: ({ signal }) => api.nodes(id, { ...filter, cursor }, signal),
    enabled: !!ready.data?.graph_analyzed,
  })
  const query = useQuery({
    queryKey: ['snapshot', id, 'neighborhood', center, direction, depth, relationship],
    queryFn: ({ signal }) => api.neighborhood(id, center, direction, depth, relationship ? [relationship] : [], signal),
    enabled: uuidPattern.test(center) && !!ready.data?.graph_analyzed,
  })
  const pathNodes = useQueries({
    queries: highlights.nodes.filter((node) => node !== center).map((node) => ({
      queryKey: ['snapshot', id, 'provenance-neighborhood', node],
      queryFn: ({ signal }: { signal: AbortSignal }) => api.neighborhood(id, node, 'outgoing', 1, [], signal),
      enabled: !!ready.data?.graph_analyzed,
    })),
    combine: (results) => ({
      nodes: results.flatMap((item) => item.data?.nodes ?? []),
      edges: results.flatMap((item) => item.data?.edges ?? []),
    }),
  })
  const mainNodes = query.data?.nodes ?? emptyNodes
  const mainEdges = query.data?.edges ?? emptyEdges
  const selected = mainNodes.find((node) => node.id === center)
  const { nodes: extras, edges: pathEdges } = pathNodes
  const displayNodes = useMemo(() => Array.from(new Map([...mainNodes, ...extras.filter((node) => highlights.nodes.includes(node.id))].map((node) => [node.id, node])).values()), [mainNodes, extras, highlights.nodes])
  const displayEdges = useMemo(() => Array.from(new Map([...mainEdges, ...pathEdges.filter((edge) => highlights.edges.includes(edge.id))]
    .filter((edge) => displayNodes.some((node) => node.id === edge.source_id) && displayNodes.some((node) => node.id === edge.target_id))
    .map((edge) => [edge.id, edge])).values()), [mainEdges, pathEdges, highlights.edges, displayNodes])
  const source = useQuery({
    queryKey: ['snapshot', id, 'source', selected?.id],
    queryFn: ({ signal }) => api.source(id, selected!.path, selected!.start_line,
      selected!.start_line == null ? null : Math.min(selected!.end_line ?? selected!.start_line + 199, selected!.start_line + 199), signal),
    enabled: inspect && !!selected,
  })
  function select(node: string, newDepth = depth) {
    setInspect(false)
    const next = new URLSearchParams(params)
    next.set('node', node)
    next.set('depth', String(newDepth))
    setParams(next)
  }
  return <div className="page-stack"><Heading eyebrow="Code relationships" title="Dependency graph">Browse stored nodes and expand a bounded, directed neighborhood.</Heading>
    {ready.isPending && <Busy>Checking graph readiness</Busy>}
    {ready.isError && <ErrorNotice error={ready.error} />}
    {ready.data && !ready.data.graph_analyzed && <Empty>Analyze this snapshot from the repository workspace before using the graph.</Empty>}
    {ready.data?.graph_analyzed && <div className="graph-layout">
      <section className="panel node-panel"><div className="panel-title"><Layers3 size={17} /><h2>Find a node</h2></div>
        <form className="pad stack" onSubmit={(event) => { event.preventDefault(); setFilter({ kind, name: name.trim(), path: path.trim() }); setCursors([null]) }}>
          <label className="field">Qualified name prefix<input maxLength={256} value={name} onChange={(e) => setName(e.target.value)} placeholder="package.module" /></label>
          <label className="field">Exact file path<input maxLength={1024} value={path} onChange={(e) => setPath(e.target.value)} placeholder="src/module.py" /></label>
          <label className="field">Node kind<select value={kind} onChange={(e) => setKind(kinds.find((item) => item === e.target.value) ?? '')}><option value="">All kinds</option>{kinds.map((item) => <option key={item}>{item}</option>)}</select></label>
          <button type="submit"><Search size={15} /> Apply filters</button>
        </form>
        {nodes.isPending && <Busy>Loading nodes</Busy>}
        {nodes.isError && <ErrorNotice error={nodes.error} />}
        {nodes.data?.items.length === 0 && <Empty>No nodes matched these filters.</Empty>}
        <ul className="node-list">{nodes.data?.items.map((node) => <li key={node.id}><button aria-pressed={center === node.id} onClick={() => select(node.id)}><i style={{ background: palette[node.kind] }} /><span><strong>{node.qualified_name}</strong><small>{node.path}</small></span></button></li>)}</ul>
        <div className="pager"><button disabled={cursors.length < 2} onClick={() => setCursors(cursors.slice(0, -1))}>Previous</button><span>Page {cursors.length}</span><button disabled={!nodes.data?.next_cursor} onClick={() => { if (nodes.data?.next_cursor) setCursors([...cursors, nodes.data.next_cursor]) }}>Next</button></div>
      </section>
      <section className="panel graph-panel">
        <div className="panel-title"><Network size={17} /><h2>Neighborhood</h2></div>
        <div className="graph-options">
          <label className="field">Direction<select value={direction} onChange={(e) => setDirection(directions.find((item) => item === e.target.value) ?? 'both')}>{directions.map((item) => <option key={item} value={item}>{item === 'both' ? 'Bidirectional' : item}</option>)}</select></label>
          <label className="field">Depth<select disabled={!center} value={depth} onChange={(e) => select(center, e.target.value === '2' ? 2 : 1)}><option value={1}>1 hop</option><option value={2}>2 hops</option></select></label>
          <label className="field">Relationship<select value={relationship} onChange={(e) => setRelationship(relationships.find((item) => item === e.target.value) ?? '')}><option value="">All relationships</option>{relationships.map((item) => <option key={item}>{item}</option>)}</select></label>
        </div>
        {!center && <Empty>Choose a node to load its neighborhood.</Empty>}
        {center && !uuidPattern.test(center) && <Empty>This node link has an invalid UUID.</Empty>}
        {query.isFetching && <Busy>Loading neighborhood</Busy>}
        {query.isError && <ErrorNotice error={query.error} />}
        {query.data && <>
          {query.data.truncated && <p role="status" className="notice">The server truncated this neighborhood. Narrow the direction, depth, or relationship.</p>}
          {highlights.edges.some((edge) => !displayEdges.some((item) => item.id === edge)) && <p className="notice">Some provenance edges are outside the loaded neighborhoods.</p>}
          <Canvas nodes={displayNodes} edges={displayEdges} center={center} nodeHighlights={highlights.nodes} edgeHighlights={highlights.edges} onSelect={select} />
          <div className="legend">{kinds.map((item) => <span key={item}><i style={{ background: palette[item] }} />{item}</span>)}<span>→ Stored edge direction</span></div>
          <section className="pad sub-divider">
            {selected && <div className="selected-node"><div><h3>{selected.qualified_name}</h3><p className="muted">{selected.kind}{selected.is_async ? ' · async' : ''} · {selected.path}{selected.start_line != null ? ':' + selected.start_line : ''}</p></div><button onClick={() => setInspect(!inspect)}>{inspect ? 'Hide source' : 'Inspect source'}</button></div>}
            <details className="text-graph"><summary>Text view · {displayNodes.length} nodes, {displayEdges.length} relationships</summary>
              <ul className="pills">{displayNodes.map((node) => <li key={node.id}><button onClick={() => select(node.id)}>{node.qualified_name}</button></li>)}</ul>
              <ul className="edge-list">{displayEdges.map((edge) => <li key={edge.id} className={highlights.edges.includes(edge.id) ? 'marked' : ''}>
                <span>{displayNodes.find((node) => node.id === edge.source_id)?.qualified_name}</span><strong>{edge.relationship} →</strong><span>{displayNodes.find((node) => node.id === edge.target_id)?.qualified_name}</span>
              </li>)}</ul>
            </details>
          </section>
        </>}
        {source.isFetching && <Busy>Loading source</Busy>}
        {source.isError && <ErrorNotice error={source.error} />}
        {inspect && source.data && <EvidencePanel evidence={source.data} start={source.data.actual_range.start_line} end={source.data.actual_range.end_line} path={source.data.path} lines={source.data.lines} url={source.data.permalink} />}
      </section>
    </div>}
  </div>
}
