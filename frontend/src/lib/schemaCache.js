const CACHE_KEY = 'erp-schema-cache-v1'
const CACHE_VERSION = 1

let memoryCache = null
let previewMemoryCache = {}

const PREVIEW_CACHE_KEY = 'erp-schema-previews-v1'

export function getMemoryCache() {
  return memoryCache
}

export function setMemoryCache(data) {
  memoryCache = data
}

export function readStorageCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed?.version !== CACHE_VERSION || !parsed?.data) return null
    return parsed
  } catch {
    return null
  }
}

export function writeStorageCache(data) {
  const entry = {
    version: CACHE_VERSION,
    storedAt: new Date().toISOString(),
    data,
  }
  localStorage.setItem(CACHE_KEY, JSON.stringify(entry))
  memoryCache = data
  return entry
}

export function readPreviewCache(tableName) {
  if (previewMemoryCache[tableName]) {
    return previewMemoryCache[tableName]
  }
  try {
    const raw = localStorage.getItem(PREVIEW_CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed?.[tableName] ?? null
  } catch {
    return null
  }
}

export function writePreviewCache(tableName, rows) {
  previewMemoryCache[tableName] = rows
  try {
    const raw = localStorage.getItem(PREVIEW_CACHE_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    parsed[tableName] = rows
    localStorage.setItem(PREVIEW_CACHE_KEY, JSON.stringify(parsed))
  } catch {
    /* ignore quota errors */
  }
}

export function clearSchemaCache() {
  memoryCache = null
  previewMemoryCache = {}
  localStorage.removeItem(CACHE_KEY)
  localStorage.removeItem(PREVIEW_CACHE_KEY)
}

export function hydrateFromCache() {
  if (memoryCache) {
    return { data: memoryCache, storedAt: memoryCache.fetched_at, from: 'memory' }
  }
  const stored = readStorageCache()
  if (stored) {
    memoryCache = stored.data
    return { data: stored.data, storedAt: stored.storedAt, from: 'storage' }
  }
  return null
}
