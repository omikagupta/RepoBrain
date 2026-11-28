import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { api, ApiError } from '../api/client'
import type { Answer } from '../api/contracts'
import { AnswerPage, SearchPage } from './retrieval'

const identity = { repository: 'owner/repo', snapshot_id: 'id', commit_sha: 'c'.repeat(40) }
const hit = { ...identity, chunk_id: 'chunk', source_file_id: 'file', path: 'reader.py', start_line: 1, end_line: 1,
  text: '<script>alert(1)</script>\r\n', score: 1, rank: 1, permalink: 'javascript:alert(1)', source_sha256: '', content_sha256: '' }
const answer: Answer = {
  ...identity, question: 'read_file', retrieval: { mode: 'graph-enhanced', chunking_version: 'fixture' },
  generator: null, prompt_version: 'fixture', status: 'answered', claims: [
    { text: '<img src=x onerror=alert(1)>', kind: 'observation', citations: ['E1'] },
  ], citations: [{ ...hit, citation_id: 'E1', provenance: null }], limitations: [],
  citation_status: 'structurally_valid', retrieved_count: 1, included_evidence_count: 1,
  context_truncated: true, evidence_bytes: 10, retrieval_ms: 1, generation_ms: 2, total_ms: 3, usage: null,
}
function mount(page: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>)
}

it('renders ranked mode-specific results and treats source as text', async () => {
  const search = vi.spyOn(api, 'search').mockResolvedValue({ ...identity, query: 'read_file', chunking_version: 'fixture', results: [hit] })
  try {
    const user = userEvent.setup()
    const view = mount(<SearchPage id="id" />)
    await user.selectOptions(screen.getByLabelText('Retrieval mode'), 'vector')
    await user.type(screen.getByLabelText('Search query'), 'read_file')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByText('Cosine similarity')).toBeInTheDocument()
    expect(screen.getByText('#1')).toBeInTheDocument()
    expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument()
    expect(view.container.querySelector('script')).toBeNull()
    expect(screen.queryByRole('link', { name: 'GitHub' })).toBeNull()
    expect(search).toHaveBeenCalledWith('id', 'vector', 'read_file', 10, expect.any(AbortSignal))
  } finally { search.mockRestore() }
})

it('opens a validated citation and renders untrusted generated text literally', async () => {
  const service = vi.spyOn(api, 'answer').mockResolvedValue(answer)
  try {
    const user = userEvent.setup()
    const view = mount(<AnswerPage id="id" />)
    await user.type(screen.getByLabelText('Repository question'), 'read_file')
    await user.click(screen.getByRole('button', { name: 'Ask RepoBrain' }))
    await user.click(await screen.findByRole('button', { name: 'E1' }))
    expect(screen.getByRole('region', { name: 'Evidence inspector' })).toHaveTextContent('reader.py')
    expect(screen.getByText(answer.claims[0].text)).toBeInTheDocument()
    expect(view.container.querySelector('img')).toBeNull()
    expect(screen.queryByText(/Input tokens/)).toBeNull()
  } finally { service.mockRestore() }
})

it('shows insufficient evidence and an unavailable provider without retries', async () => {
  const service = vi.spyOn(api, 'answer').mockResolvedValueOnce({
    ...answer, status: 'insufficient_evidence', claims: [], citations: [], limitations: ['No relevant evidence.'],
  }).mockRejectedValueOnce(new ApiError(503, 'generation_unavailable', 'req', 'Configure generation.'))
  try {
    const user = userEvent.setup()
    mount(<AnswerPage id="id" />)
    await user.type(screen.getByLabelText('Repository question'), 'read_file')
    const submit = screen.getByRole('button', { name: 'Ask RepoBrain' })
    await user.click(submit)
    expect(await screen.findByRole('heading', { name: 'Insufficient evidence' })).toBeInTheDocument()
    await user.click(submit)
    expect(await screen.findByRole('alert')).toHaveTextContent('Configure generation.')
    expect(service).toHaveBeenCalledTimes(2)
  } finally { service.mockRestore() }
})
