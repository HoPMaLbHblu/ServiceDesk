/**
 * Per-browser UI preferences. Only identifiers the server re-validates are kept
 * here; business records are never written to local storage.
 */
const LAST_WORKSPACE = 'servicedesk.lastWorkspace'

function read(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(LAST_WORKSPACE) ?? '{}') as Record<string, string>
  } catch {
    return {}
  }
}

export function lastWorkspaceFor(userId: string): string | null {
  return read()[userId] ?? null
}

export function rememberWorkspace(userId: string, businessId: string): void {
  try {
    localStorage.setItem(LAST_WORKSPACE, JSON.stringify({ ...read(), [userId]: businessId }))
  } catch {
    /* storage unavailable */
  }
}
