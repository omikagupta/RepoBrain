import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const hosted = command === 'build' && env.VITE_DEPLOYMENT_MODE === 'hosted'
  const hostedPolicy = {
    name: 'repobrain-hosted-csp',
    transformIndexHtml() {
      const api = new URL(env.VITE_API_BASE_URL)
      const auth = new URL(env.VITE_SUPABASE_URL)
      if (api.protocol !== 'https:' || auth.protocol !== 'https:' ||
        api.origin !== env.VITE_API_BASE_URL || auth.origin !== env.VITE_SUPABASE_URL) {
        throw new Error('Hosted build requires exact HTTPS API and Auth origins')
      }
      return [{
        tag: 'meta',
        attrs: {
          'http-equiv': 'Content-Security-Policy',
          content: "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
            "img-src 'self' data:; font-src 'self'; connect-src 'self' " + api.origin + ' ' + auth.origin +
            "; base-uri 'none'; form-action 'self'; object-src 'none'",
        },
        injectTo: 'head-prepend' as const,
      }]
    },
  }
  return {
    plugins: [react(), tailwindcss(), ...(hosted ? [hostedPolicy] : [])],
    server: {
      host: '127.0.0.1',
      proxy: { '/api': env.BACKEND_PROXY_TARGET || 'http://127.0.0.1:8000' },
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.{ts,tsx}'],
      setupFiles: ['./src/test/setup.ts'],
    },
  }
})
