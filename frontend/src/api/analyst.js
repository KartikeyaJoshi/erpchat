const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export function getApiBaseUrl() {
  return API_BASE
}

export function isApiConfigured() {
  return Boolean(API_BASE) || !import.meta.env.PROD
}

/**
 * @param {string} query
 * @param {Record<string, string>} [resolvedFilters]
 */
export async function analyzeQuery(query, resolvedFilters = {}) {
  const body = { query: query.trim() }
  if (resolvedFilters && Object.keys(resolvedFilters).length > 0) {
    body.resolved_filters = resolvedFilters
  }

  const response = await fetch(`${API_BASE}/api/v1/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(body),
  })

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    const message =
      data?.error?.message ||
      data?.detail?.message ||
      (typeof data?.detail === 'string' ? data.detail : null) ||
      `Request failed (${response.status})`
    throw new Error(message)
  }

  return data
}

export async function checkHealth() {
  const response = await fetch(`${API_BASE}/health`)
  if (!response.ok) {
    throw new Error('API unreachable')
  }
  return response.json()
}
