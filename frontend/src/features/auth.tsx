import { createClient, type Session } from '@supabase/supabase-js'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { setApiSession } from '../api/client'
import { Busy } from '../ui'

export const hosted = import.meta.env.VITE_DEPLOYMENT_MODE === 'hosted'
const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY
// The publishable key is a public project identifier, never a service role key.
const client = hosted && url && key?.startsWith('sb_publishable_')
  ? createClient(url, key, { auth: { flowType: 'pkce' } }) : null

export async function signOut() {
  if (!client) return
  const { error } = await client.auth.signOut({ scope: 'local' })
  if (error) throw new Error('Sign out failed. Try again.')
}

function Login() {
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [signup, setSignup] = useState(false)
  const [notice, setNotice] = useState('')
  async function login() {
    if (!client || pending) return
    setPending(true)
    setError('')
    setNotice('')
    try {
      const result = signup
        ? await client.auth.signUp({ email, password, options: { emailRedirectTo: new URL('/login', window.location.origin).href } })
        : await client.auth.signInWithPassword({ email, password })
      if (result.error) throw result.error
      if (signup) setNotice('Check your email to confirm your account.')
    } catch {
      setError(signup ? 'Registration could not be completed.' : 'Sign-in failed. Check your details and try again.')
    } finally {
      setPending(false)
    }
  }
  return <main className="main page-stack">
    <h1>{signup ? 'Create a RepoBrain account' : 'Sign in to RepoBrain'}</h1>
    {client ? <form className="panel pad stack" onSubmit={(event) => { event.preventDefault(); void login() }}>
      <label className="field">Email<input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
      <label className="field">Password<input type="password" required minLength={8} autoComplete={signup ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      <button className="button primary" disabled={pending}>{signup ? 'Create account' : 'Sign in'}</button>
      <button type="button" disabled={pending} onClick={() => { setSignup(!signup); setError(''); setNotice('') }}>{signup ? 'Back to sign in' : 'Create an account'}</button>
    </form>
      : <p role="alert">Sign-in configuration is unavailable.</p>}
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
  </main>
}

export function AuthBoundary({ children }: { children: ReactNode }) {
  const query = useQueryClient()
  const [session, setSession] = useState<Session | null | undefined>(client ? undefined : null)
  useEffect(() => {
    if (!client) return
    let current: string | undefined
    let active = true
    const expire = () => {
      if (!active) return
      setApiSession()
      current = undefined
      query.clear()
      setSession(null)
      window.setTimeout(() => { if (active && !current) void signOut().catch(() => undefined) }, 0)
    }
    const { data: { subscription } } = client.auth.onAuthStateChange((_event, next) => {
      if (!active) return
      if (current !== next?.user.id) query.clear()
      current = next?.user.id
      setApiSession(next?.access_token, expire)
      setSession(next)
    })
    return () => { active = false; subscription.unsubscribe(); setApiSession(); query.clear() }
  }, [query])
  if (session === undefined) return <Busy>Checking session</Busy>
  if (!session) return <Routes><Route path="/login" element={<Login />} />
    <Route path="*" element={<Navigate to="/login" replace />} /></Routes>
  return <div key={session.user.id}>{children}</div>
}
