/**
 * Fetch wrapper for the ServiceDesk API.
 *
 * - Same-origin session cookie; never stores credentials in JS-accessible storage.
 * - Sends the CSRF token on unsafe requests.
 * - Turns error responses into ApiError with field-level messages.
 * - Reports 401 responses so the session store can handle expiry.
 */

export interface ApiErrorBody {
  code: string
  message: string
  fields: Record<string, unknown>
  details: Record<string, unknown>
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields: Record<string, string[]>
  readonly details: Record<string, unknown>

  constructor(status: number, body: Partial<ApiErrorBody>) {
    super(body.message || `Request failed (${status})`)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code || 'error'
    this.fields = flattenFields(body.fields ?? {})
    this.details = body.details ?? {}
  }

  get isConflict(): boolean {
    return this.status === 409
  }
}

/** Nested serializer errors such as {lines: [{quantity: [...]}]} become {"lines.0.quantity": [...]}. */
export function flattenFields(fields: Record<string, unknown>, prefix = ''): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  for (const [key, value] of Object.entries(fields)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (Array.isArray(value) && value.every((v) => typeof v === 'string')) {
      out[path] = value as string[]
    } else if (Array.isArray(value)) {
      value.forEach((item, index) => {
        if (item && typeof item === 'object') Object.assign(out, flattenFields(item as Record<string, unknown>, `${path}.${index}`))
      })
    } else if (value && typeof value === 'object') {
      Object.assign(out, flattenFields(value as Record<string, unknown>, path))
    } else if (typeof value === 'string') {
      out[path] = [value]
    }
  }
  return out
}

type Query = Record<string, string | number | boolean | null | undefined | string[]>

export interface RequestOptions {
  query?: Query
  body?: unknown
  signal?: AbortSignal
}

type UnauthorizedListener = (url: string) => void
let unauthorizedListener: UnauthorizedListener | null = null

export function onUnauthorized(listener: UnauthorizedListener | null): void {
  unauthorizedListener = listener
}

export function readCookie(name: string): string | null {
  const match = document.cookie.split('; ').find((part) => part.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null
}

export function buildUrl(path: string, query?: Query): string {
  const url = new URL(path.startsWith('/api/') ? path : `/api/v1${path}`, window.location.origin)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) value.forEach((v) => url.searchParams.append(key, v))
    else url.searchParams.set(key, String(value))
  }
  return url.pathname + url.search
}

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

async function send(method: string, path: string, options: RequestOptions = {}): Promise<Response> {
  const url = buildUrl(path, options.query)
  const headers: Record<string, string> = { Accept: 'application/json' }
  let body: BodyInit | undefined
  if (options.body instanceof FormData) {
    body = options.body
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  if (UNSAFE.has(method)) {
    const token = readCookie('csrftoken')
    if (token) headers['X-CSRFToken'] = token
  }
  const response = await fetch(url, { method, headers, body, credentials: 'same-origin', signal: options.signal })
  if (!response.ok) {
    let parsed: Partial<ApiErrorBody> = {}
    try {
      const json = (await response.json()) as { error?: Partial<ApiErrorBody> }
      parsed = json.error ?? {}
    } catch {
      parsed = { code: 'http_error', message: response.statusText || `Request failed (${response.status})` }
    }
    if (response.status === 401 && unauthorizedListener && !url.startsWith('/api/v1/auth/')) {
      unauthorizedListener(url)
    }
    throw new ApiError(response.status, parsed)
  }
  return response
}

export async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(method, path, options)
  if (response.status === 204) return undefined as T
  const type = response.headers.get('Content-Type') ?? ''
  if (!type.includes('json')) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>('GET', path, { query, signal }),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, { body }),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, { body }),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, { body }),
  delete: <T>(path: string) => request<T>('DELETE', path),
}

/** Download a file through the authenticated session and hand it to the browser. */
export async function download(path: string, fallbackName: string, query?: Query): Promise<void> {
  const response = await send('GET', path, { query })
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallbackName
  const href = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = href
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(href), 1000)
}
