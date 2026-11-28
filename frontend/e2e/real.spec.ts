import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const id = '9bdaf39e-b9e0-4acf-89a5-0bfcdda66f53'
const artifacts = process.env.REPOBRAIN_SCREENSHOTS
async function capture(page: Page, name: string) {
  if (!artifacts) return
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: artifacts + '/' + name + '.png', fullPage: true })
}
test('production frontend through real FastAPI and PostgreSQL', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/repositories')
  await page.getByLabel('Snapshot UUID').fill(id)
  await page.getByRole('button', { name: 'Open snapshot' }).click()
  await expect(page.getByText('Graph nodes', { exact: true })).toBeVisible()
  await expect(page.getByText('cosine-exact-v1', { exact: true })).toBeVisible()
  await capture(page, 'overview')

  await page.getByRole('link', { name: 'Code search', exact: true }).click()
  await page.getByLabel('Search query').fill('read_file')
  await page.getByLabel('Retrieval mode').selectOption('lexical')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Search results' })).toContainText('reader.py')
  await capture(page, 'search')

  await page.getByRole('link', { name: 'Dependency graph' }).click()
  await page.getByRole('button', { name: /app\s*app\.py/ }).click()
  await page.getByText(/Text view/).click()
  await expect(page.locator('.edge-list')).toContainText('IMPORTS')
  await expect(page.locator('.graph-canvas canvas').first()).toBeVisible()
  await capture(page, 'graph')

  await page.getByRole('link', { name: 'AI answers' }).click()
  await page.getByLabel('Repository question').fill('read_file')
  await page.getByRole('button', { name: 'Ask RepoBrain' }).click()
  await expect(page.getByText('Deterministic test demonstration.')).toBeVisible()
  await page.getByRole('button', { name: /^E\d+$/ }).click()
  const evidence = page.getByRole('region', { name: 'Evidence inspector' })
  await expect(evidence).toContainText('read_file')
  await expect(evidence.getByRole('link', { name: 'GitHub' })).toHaveAttribute('href', /https:\/\/github\.com\/sample\/.*\/blob\/c{40}\/.+\.py#L/)
  await capture(page, 'answer')

  await page.setViewportSize({ width: 390, height: 844 })
  for (const tab of ['Overview', 'Dependency graph', 'AI answers', 'Code search']) {
    await page.getByRole('navigation', { name: 'Workspace' }).getByRole('link', { name: tab, exact: true }).click()
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  }
  await page.getByLabel('Search query').fill('read_file')
  await page.getByLabel('Retrieval mode').selectOption('lexical')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Search results' })).toContainText('reader.py')
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await capture(page, 'mobile-search')
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Code search' })).toBeVisible()
  expect(errors).toEqual([])
})
