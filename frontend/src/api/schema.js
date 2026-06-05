const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

/**
 * @param {{ refresh?: boolean }} [options]
 */
export async function fetchSchema({ refresh = false } = {}) {
  const params = refresh ? '?refresh=true' : ''
  const response = await fetch(`${API_BASE}/api/v1/schema${params}`, {
    headers: { Accept: 'application/json' },
  })

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    const message =
      data?.detail?.message ||
      (typeof data?.detail === 'string' ? data.detail : null) ||
      `Schema request failed (${response.status})`
    throw new Error(message)
  }

  return data
}

/**
 * @param {string} tableName
 */
export async function fetchTablePreview(tableName) {
  const response = await fetch(
    `${API_BASE}/api/v1/schema/tables/${encodeURIComponent(tableName)}/preview`,
    { headers: { Accept: 'application/json' } },
  )

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    const message =
      data?.detail ||
      (typeof data?.detail === 'string' ? data.detail : null) ||
      `Preview request failed (${response.status})`
    throw new Error(message)
  }

  return data
}
