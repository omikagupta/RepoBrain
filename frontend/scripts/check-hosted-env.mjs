import process from 'node:process'
import { URL } from 'node:url'

function origin(name) {
  const raw = process.env[name]
  try {
    const parsed = new URL(raw)
    if (parsed.protocol === 'https:' && parsed.origin === raw) return parsed.origin
  } catch {
    // Build errors contain variable names only.
  }
  throw new Error(name + ' must be an exact HTTPS origin')
}

if (process.env.VITE_DEPLOYMENT_MODE !== 'hosted') throw new Error('Hosted mode is required')
origin('VITE_API_BASE_URL')
origin('VITE_SUPABASE_URL')
if (!/^sb_publishable_[A-Za-z0-9_-]+$/.test(process.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? '')) {
  throw new Error('VITE_SUPABASE_PUBLISHABLE_KEY must be a publishable key')
}
