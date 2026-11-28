import { describe, expect, it, vi } from 'vitest'
import { api } from './client'
import { pinnedLink, sourceLines, validRepository } from './validation'

describe('API boundary', () => {
  it('encodes query values and forwards cancellation', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ results: [] })))
    try {
      const controller = new AbortController()
      await expect(api.search('test', 'lexical', 'r&x=1', 5, controller.signal)).resolves.toEqual({ results: [] })
      expect(fetcher).toHaveBeenCalledWith('/api/v1/snapshots/test/search/lexical?q=r%26x%3D1&limit=5',
        expect.objectContaining({ signal: controller.signal, redirect: 'error' }))
    } finally { fetcher.mockRestore() }
  })

  it('maps backend errors and retains their request ID', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'generation_unavailable', request_id: 'req-1' },
    }), { status: 503 }))
    try {
      await expect(api.answer('test', 'question', 'lexical')).rejects.toMatchObject({
        status: 503, requestId: 'req-1', message: expect.stringContaining('backend environment'),
      })
    } finally { fetcher.mockRestore() }
  })

  it('checks repository names and exact commit-pinned links', () => {
    const context = { repository: 'owner/repo', commit_sha: 'c'.repeat(40), snapshot_id: 'snapshot' }
    const href = 'https://github.com/owner/repo/blob/' + context.commit_sha + '/src/a%20%23.py#L1-L2'
    expect(validRepository('owner/repo')).toBe(true)
    expect(validRepository('https://github.com/owner/repo')).toBe(false)
    expect(validRepository('owner/..')).toBe(false)
    expect(pinnedLink(context, 'src/a #.py', 1, 2, href)).toBe(href)
    for (const unsafe of ['javascript:alert(1)', href.replace('github.com', 'github.com.evil'), href.replace('#L1-L2', '#L3')])
      expect(pinnedLink(context, 'src/a #.py', 1, 2, unsafe)).toBeNull()
    expect(sourceLines('a\r\nb\rc\n')).toEqual(['a', 'b', 'c'])
  })

  it('shows the retry delay for a throttled lexical search', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'lexical_limit', message: 'Usage limit reached.' },
    }), { status: 429, headers: { 'Retry-After': '42' } }))
    try {
      await expect(api.search('test', 'lexical', 'code', 5)).rejects.toMatchObject({
        status: 429, retryAfter: 42, message: expect.stringContaining('42 seconds'),
      })
    } finally { fetcher.mockRestore() }
  })
})
