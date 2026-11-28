import { expect, test } from '@playwright/test'

const id = '9bdaf39e-b9e0-4acf-89a5-0bfcdda66f53'
const second = '9bdaf39e-b9e0-4acf-89a5-0bfcdda66f54'
const sha = 'a'.repeat(40)
const identity = { snapshot_id: id, repository: 'test/repository', commit_sha: sha }
test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/ingestions/*', (route) => route.fulfill({ json: {
    ...(route.request().url().endsWith(second) ? { ...identity, snapshot_id: second, repository: 'test/second' } : identity),
    state: 'completed', file_count: 1, error: null,
  } }))
  await page.route('**/readiness', (route) => route.fulfill({ json: {
    ...identity, graph_analyzed: false, lexical_version: null, vector_version: null,
  } }))
})

test('skip link moves keyboard focus to the workspace', async ({ page }) => {
  await page.goto('/repositories')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('main')).toBeFocused()
})

test('reopens a snapshot, switches snapshot and handles a missing index', async ({ page }) => {
  await page.goto('/repositories')
  await page.getByLabel('GitHub repository').fill('https://unsafe.example/repo')
  await page.getByRole('button', { name: 'Start ingestion' }).click()
  await expect(page.getByRole('alert')).toContainText('owner/name')
  await page.getByLabel('Snapshot UUID').fill(id)
  await page.getByRole('button', { name: 'Open snapshot' }).click()
  await expect(page.getByRole('heading', { name: identity.repository })).toBeVisible()
  await page.getByRole('link', { name: 'Code search', exact: true }).click()
  await page.route('**/search/vector?*', (route) => route.fulfill({ status: 409, json: {
    error: { code: 'vector_index_unavailable', message: 'Missing index', request_id: 'fixture-request' },
  } }))
  await page.getByLabel('Retrieval mode').selectOption('vector')
  await page.getByLabel('Search query').fill('read_file')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Build the vector index')
  await expect(page.getByRole('alert')).toContainText('fixture-request')
  await page.getByRole('link', { name: 'Switch snapshot' }).click()
  await page.getByLabel('Snapshot UUID').fill(second)
  await page.getByRole('button', { name: 'Open snapshot' }).click()
  await expect(page.getByRole('heading', { name: 'test/second' })).toBeVisible()
})

test('cancels answer without duplicate posts and ignores a late response', async ({ page }) => {
  let finish: () => void = () => {}
  const paused = new Promise<void>((resolve) => { finish = resolve })
  let posts = 0
  await page.route('**/answer', async (route) => {
    posts++
    await paused
    await route.fulfill({ status: 503, json: {
      error: { code: 'generation_unavailable', message: 'Unavailable', request_id: 'late' },
    } }).catch(() => {})
  })
  try {
    await page.goto('/snapshots/' + id + '/answers')
    await page.getByLabel('Repository question').fill('read_file')
    const submit = page.getByRole('button', { name: 'Ask RepoBrain' })
    await submit.click()
    await expect(submit).toBeDisabled()
    await expect.poll(() => posts).toBe(1)
    await page.getByRole('button', { name: 'Cancel answer' }).click()
    finish()
    await expect(page.getByText(/Browser request cancelled/)).toBeVisible()
    await expect(page.getByText('late', { exact: true })).toHaveCount(0)
  } finally { finish() }
})

test('filters graph and shows server truncation and textual edges', async ({ page }) => {
  const node = { id, snapshot_id: id, kind: 'module', qualified_name: 'entry', path: 'entry.py',
    start_line: 1, end_line: 1, is_async: false }
  const other = { ...node, id: second, qualified_name: 'reader', path: 'reader.py' }
  await page.route('**/readiness', (route) => route.fulfill({ json: {
    ...identity, graph_analyzed: true, lexical_version: null, vector_version: null,
  } }))
  await page.route('**/nodes?*', (route) => route.fulfill({ json: { items: [node], next_cursor: null } }))
  await page.route('**/neighborhood?*', (route) => route.fulfill({ json: {
    snapshot_id: id, center_node_id: id, depth: 1, truncated: true, nodes: [node, other],
    edges: [{ id: 'edge', snapshot_id: id, source_id: id, target_id: second,
      relationship: 'IMPORTS', line: 1, column: 0, provenance: 'fixture' }],
  } }))
  await page.goto('/snapshots/' + id + '/graph')
  await page.getByLabel('Node kind').selectOption('module')
  const filtered = page.waitForRequest((request) => request.url().includes('/nodes?limit=24&kind=module'))
  await page.getByRole('button', { name: 'Apply filters' }).click()
  await filtered
  await page.getByRole('button', { name: /entry\s*entry\.py/ }).click()
  await expect(page.getByText(/server truncated/)).toBeVisible()
  const imports = page.waitForRequest((request) => request.url().includes('relationship=IMPORTS'))
  await page.getByLabel('Relationship').selectOption('IMPORTS')
  await imports
  await page.getByText(/Text view/).click()
  await expect(page.locator('.edge-list')).toContainText(/entry\s*IMPORTS →\s*reader/)
})
