import { useState } from 'react'
import { hosted } from './auth'
import type { FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleStop, FileCode2, Search, Sparkles } from 'lucide-react'
import { api } from '../api/client'
import type { Answer, Mode, SearchResponse } from '../api/contracts'
import { Busy, Empty, ErrorNotice, EvidencePanel, Heading, ModeSelect, Policies, ProvenancePanel, modes } from '../ui'

interface Submission { text: string; mode: Mode; limit: number; sequence: number }
function useSubmission<T>(id: string, name: string, execute: (input: Submission, signal: AbortSignal) => Promise<T>) {
  const [sequence, setSequence] = useState(0)
  const [submission, setSubmission] = useState<Submission | null>(null)
  const [cancelled, setCancelled] = useState(false)
  const queryClient = useQueryClient()
  const key = ['snapshot', id, name, submission] as const
  const result = useQuery({
    queryKey: key, enabled: submission !== null,
    queryFn: ({ signal }) => execute(submission!, signal),
    retry: false, gcTime: 0, staleTime: Infinity, refetchOnReconnect: false,
  })
  const running = submission !== null && (result.isFetching || result.isPending)
  function submit(text: string, mode: Mode, limit = 10) {
    if (running || !text.trim() || text.includes('\0')) return false
    setSequence(sequence + 1)
    setSubmission({ text: text.trim(), mode, limit, sequence })
    setCancelled(false)
    return true
  }
  function cancel() {
    void queryClient.cancelQueries({ queryKey: key, exact: true })
    setSubmission(null)
    setCancelled(true)
  }
  return { result, running, cancelled, submission, submit, cancel }
}

export function SearchPage({ id }: { id: string }) {
  const [text, setText] = useState('')
  const [mode, setMode] = useState<Mode>(hosted ? 'lexical' : 'hybrid')
  const [limit, setLimit] = useState('10')
  const request = useSubmission<SearchResponse>(id, 'search', (input, signal) => api.search(id, input.mode, input.text, input.limit, signal))
  const results = request.result.data
  const submittedMode = modes.find((entry) => entry.id === request.submission?.mode)
  return <div className="page-stack">
    <Heading eyebrow="Retrieval" title="Code search">Find source evidence in this snapshot using one of four retrieval modes.</Heading>
    <form className="panel pad stack" onSubmit={(e: FormEvent) => {
      e.preventDefault()
      if (Number(limit) >= 1 && Number(limit) <= 30) request.submit(text, mode, Number(limit))
    }}>
      <label className="field">Search query<input placeholder="Search a symbol, concept, or code token" required maxLength={mode === 'vector' ? 512 : 256} value={text} onChange={(event) => setText(event.target.value)} /></label>
      <div className="form-row">{hosted
        ? <p>Lexical search is available. Vector, hybrid, graph-enhanced retrieval and AI answers are disabled in hosted mode.</p>
        : <ModeSelect mode={mode} onChange={setMode} />}
        <label className="field limit">Result limit<input type="number" min={1} max={30} required value={limit} onChange={(e) => setLimit(e.target.value)} /></label>
        <button className="primary" disabled={request.running || !text.trim()}><Search size={16} /> Search</button>
        {request.running && <button type="button" onClick={request.cancel}><CircleStop size={16} /> Cancel search</button>}
      </div>
    </form>
    {request.running && <Busy>Searching pinned source</Busy>}
    {request.cancelled && <Empty>Search cancelled.</Empty>}
    {request.result.isError && <ErrorNotice error={request.result.error} />}
    {results && <section className="stack" aria-label="Search results">
      <div className="result-heading"><div><h2>{results.results.length} {results.results.length === 1 ? 'result' : 'results'}</h2><p className="muted">{submittedMode?.title} for “{results.query}”. Scores are specific to the selected mode.</p></div><Policies policy={results} /></div>
      {results.traversal?.truncated && <p className="notice">Graph expansion reached a server limit. Results include the bounded portion.</p>}
      {!results.results.length && <Empty>No source matched this query in the selected mode.</Empty>}
      {results.results.map((hit) => <article key={hit.chunk_id} className="result">
        <div className="result-meta"><span className="rank">#{hit.rank}</span><strong>{submittedMode?.score} <code>{hit.score.toPrecision(6)}</code></strong>
          {hit.channels?.map((channel) => <span key={channel} className="badge">{channel}</span>)}
          {hit.lexical_rank != null && <span>Lexical rank {hit.lexical_rank} · <code>{hit.lexical_score?.toPrecision(6)}</code></span>}
          {hit.vector_rank != null && <span>Vector rank {hit.vector_rank} · <code>{hit.vector_score?.toPrecision(6)}</code></span>}
          {hit.hybrid_rank != null && <span>Hybrid rank {hit.hybrid_rank} · <code>{hit.hybrid_score?.toPrecision(6)}</code></span>}
          {hit.graph_contribution !== undefined && <span>Graph contribution <code>{hit.graph_contribution.toPrecision(6)}</code></span>}
        </div>
        <EvidencePanel evidence={hit} path={hit.path} start={hit.start_line} end={hit.end_line} text={hit.text} url={hit.permalink}>
          {hit.provenance && <ProvenancePanel snapshot={id} provenance={hit.provenance} />}
        </EvidencePanel>
      </article>)}
    </section>}
  </div>
}

export function AnswerPage({ id }: { id: string }) {
  const [text, setText] = useState('')
  const [mode, setMode] = useState<Mode>('graph-enhanced')
  const [citationId, setCitationId] = useState('')
  const request = useSubmission<Answer>(id, 'answer', (input, signal) => api.answer(id, input.text, input.mode, signal))
  const answer = request.result.data
  const citation = answer?.citations.find((item) => item.citation_id === citationId)
  return <div className="page-stack">
    <Heading eyebrow="Evidence-grounded generation" title="AI answers">Ask a question about this repository and inspect the source behind each claim.</Heading>
    <form className="panel pad stack" onSubmit={(e) => {
      e.preventDefault()
      if (request.submit(text, mode)) setCitationId('')
    }}>
      <div className="field"><label htmlFor="repository-question">Repository question</label><textarea id="repository-question" aria-describedby="question-length" required maxLength={256} value={text} placeholder="How does repository ingestion work?" onChange={(event) => setText(event.target.value)} /><small id="question-length">{text.length}/256 characters</small></div>
      <div className="form-row"><ModeSelect mode={mode} onChange={setMode} />
        <button className="primary" disabled={request.running || !text.trim()}><Sparkles size={16} /> Ask RepoBrain</button>
        {request.running && <button type="button" onClick={request.cancel}><CircleStop size={16} /> Cancel answer</button>}
      </div>
    </form>
    <div className="notice plain-note">Answers are AI-generated from retrieved source. Citations are structurally validated and semantic correctness is not guaranteed. A configured remote provider receives the question and selected excerpts.</div>
    {request.running && <Busy>Generating an answer from pinned source evidence</Busy>}
    {request.cancelled && <Empty>Browser request cancelled. Upstream computation or billing may continue.</Empty>}
    {request.result.isError && <ErrorNotice error={request.result.error} />}
    {answer && <section className="answer-layout" aria-label="Grounded answer">
      <div className="panel"><div className="panel-title"><Sparkles size={17} /><h2>{answer.status === 'answered' ? 'Generated answer' : 'Insufficient evidence'}</h2></div>
        <div className="pad stack"><p className="answer-question">{answer.question}</p>
          {answer.claims.map((claim, index) => <div className="claim" key={index}>
            <span className={'badge ' + claim.kind}>{claim.kind}</span><p>{claim.text}</p>
            <div className="pills">{claim.citations.map((citation) => <button type="button" key={citation} aria-pressed={citationId === citation} className="evidence-id" onClick={() => setCitationId(citation)}>{citation}</button>)}</div>
          </div>)}
          {answer.limitations.length > 0 && <div><h3>Evidence limitations</h3><ul className="bullets">{answer.limitations.map((entry, index) => <li key={index}>{entry}</li>)}</ul></div>}
          {answer.context_truncated && <p className="notice">The evidence context was truncated to fit its budget.</p>}
          <div className="sub-divider telemetry">
            <span>{answer.included_evidence_count}/{answer.retrieved_count} evidence chunks · {answer.evidence_bytes.toLocaleString()} bytes</span>
            <span>Retrieval {answer.retrieval_ms.toFixed(1)} ms {answer.generation_ms != null && '· generation ' + answer.generation_ms.toFixed(1) + ' ms'}</span>
            {answer.usage?.input_tokens != null && <span>Input tokens {answer.usage.input_tokens}</span>}
            {answer.usage?.output_tokens != null && <span>Output tokens {answer.usage.output_tokens}</span>}
            {answer.generator && <span>{answer.generator.provider} · {answer.generator.model}</span>}
            <code>{answer.prompt_version}</code>
          </div><Policies policy={answer.retrieval} />
        </div>
      </div>
      <div className="stack">{citation ? <EvidencePanel key={citationId} evidence={citation} path={citation.path} start={citation.start_line} end={citation.end_line} text={citation.text} url={citation.permalink}>
        {citation.provenance && <ProvenancePanel snapshot={id} provenance={citation.provenance} />}
      </EvidencePanel> : answer.citations.length > 0 && <section className="panel pad"><h2><FileCode2 size={17} /> Evidence inspector</h2><p className="muted">Select an evidence ID to open the canonical source.</p></section>}</div>
    </section>}
  </div>
}
