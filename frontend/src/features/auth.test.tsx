import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

const mock = vi.hoisted(() => {
  let change: (event: string, session: unknown) => void = () => undefined
  return {
    login: vi.fn(async () => ({ error: null })),
    logout: vi.fn(async () => ({ error: null })),
    emit: (session: unknown) => change('TEST', session),
    subscribe: (callback: typeof change) => {
      change = callback
      callback('INITIAL_SESSION', null)
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    },
  }
})

vi.mock('@supabase/supabase-js', () => ({
  createClient: () => ({ auth: {
    onAuthStateChange: mock.subscribe,
    signInWithPassword: mock.login,
    signOut: mock.logout,
  } }),
}))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

it('guards deep links, uses the active token and clears session and cache on 401', async () => {
  vi.stubEnv('VITE_DEPLOYMENT_MODE', 'hosted')
  vi.stubEnv('VITE_SUPABASE_URL', 'http://127.0.0.1:54321')
  vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_test')
  const { AuthBoundary } = await import('./auth')
  const { api } = await import('../api/client')
  const fetcher = vi.fn(async (_url: string, options: RequestInit) => {
    expect(options.headers).toMatchObject({ Authorization: 'Bearer signed-token' })
    return new Response('{}', { status: 401 })
  })
  vi.stubGlobal('fetch', fetcher)
  const cache = new QueryClient()
  render(<QueryClientProvider client={cache}><MemoryRouter initialEntries={['/snapshots/sensitive']}>
    <AuthBoundary><div>Private workspace contents</div></AuthBoundary>
  </MemoryRouter></QueryClientProvider>)
  expect(await screen.findByRole('heading', { name: 'Sign in to RepoBrain' })).toBeVisible()
  expect(screen.queryByText('Private workspace contents')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'local@example.invalid' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await waitFor(() => expect(mock.login).toHaveBeenCalledWith({ email: 'local@example.invalid', password: 'test-password' }))
  act(() => mock.emit({ user: { id: 'user-a' }, access_token: 'signed-token' }))
  expect(await screen.findByText('Private workspace contents')).toBeVisible()
  cache.setQueryData(['workspace'], { private: true })
  await act(async () => { await expect(api.workspace()).rejects.toMatchObject({ status: 401 }) })
  expect(await screen.findByRole('heading', { name: 'Sign in to RepoBrain' })).toBeVisible()
  expect(cache.getQueryData(['workspace'])).toBeUndefined()
})
