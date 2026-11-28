import { defineConfig, devices } from '@playwright/test'

const real = Boolean(process.env.REPOBRAIN_E2E_BASE)
export default defineConfig({
  testDir: './e2e',
  testMatch: real ? '**/real.spec.ts' : '**/mocked.spec.ts',
  timeout: 30_000,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.REPOBRAIN_E2E_BASE || 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
  },
  webServer: real ? undefined : { command: 'npm run dev -- --port 4173 --strictPort', url: 'http://127.0.0.1:4173' },
})
