import { vi } from 'vitest'

type Handler = (init: RequestInit & { url: string; json: unknown }) => { status?: number; body?: unknown } | undefined

/**
 * Replace fetch with a small router: `{ 'GET /api/v1/orders/': () => ({ body }) }`.
 * Unmatched requests fail the test loudly. Every call is recorded.
 */
export function mockFetch(routes: Record<string, Handler>) {
  const calls: { method: string; url: string; json: unknown; headers: Record<string, string> }[] = []
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input)
    const method = (init.method ?? 'GET').toUpperCase()
    const json = typeof init.body === 'string' ? JSON.parse(init.body) : init.body
    calls.push({ method, url, json, headers: (init.headers ?? {}) as Record<string, string> })
    const path = url.split('?')[0]
    const handler = routes[`${method} ${path}`] ?? routes[`${method} ${url}`]
    if (!handler) throw new Error(`Unexpected request: ${method} ${url}`)
    const result = handler({ ...init, url, json }) ?? {}
    const status = result.status ?? 200
    return new Response(status === 204 ? null : JSON.stringify(result.body ?? {}), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fn)
  return { fn, calls }
}

export function sessionFor(role: 'owner' | 'manager' | 'technician' | null, workspace = { id: 'ws-a', name: 'Alpha Repairs' }) {
  const user = { id: 'user-1', email: 'sam@example.com', full_name: 'Sam Smith', email_verified: true }
  return {
    authenticated: true,
    user,
    memberships: role
      ? [
          { business_id: 'ws-a', business_name: 'Alpha Repairs', role },
          { business_id: 'ws-b', business_name: 'Beta Fixers', role: 'technician' },
        ]
      : [],
    portal_links: [],
    active_workspace: role ? { ...workspace, role, timezone: 'Europe/London', currency: 'GBP' } : null,
  }
}
