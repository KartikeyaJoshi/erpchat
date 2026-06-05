import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react'
import { fetchSchema } from '../api/schema'
import {
  clearSchemaCache,
  hydrateFromCache,
  writeStorageCache,
} from '../lib/schemaCache'

const SchemaContext = createContext(null)

export function SchemaProvider({ children }) {
  const initial = hydrateFromCache()
  const [data, setData] = useState(initial?.data ?? null)
  const [loading, setLoading] = useState(!initial?.data)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [cacheSource, setCacheSource] = useState(initial?.from ?? null)
  const [cachedAt, setCachedAt] = useState(initial?.storedAt ?? null)
  const fetchedRef = useRef(!!initial?.data)

  const [selectedTable, setSelectedTable] = useState(null)
  const [search, setSearch] = useState('')
  const [showRelations, setShowRelations] = useState(false)
  const [previews, setPreviews] = useState({})

  const applyPayload = useCallback((payload, source) => {
    writeStorageCache(payload)
    setData(payload)
    setCacheSource(source)
    setCachedAt(payload.fetched_at || new Date().toISOString())
  }, [])

  const load = useCallback(async (refresh = false) => {
    if (refresh) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    setError(null)

    try {
      const payload = await fetchSchema({ refresh })
      applyPayload(payload, 'network')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load schema')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [applyPayload])

  useEffect(() => {
    if (!fetchedRef.current) {
      fetchedRef.current = true
      load(false)
    }
  }, [load])

  const refresh = useCallback(async () => {
    clearSchemaCache()
    setPreviews({})
    await load(true)
  }, [load])

  const retry = useCallback(async () => {
    await load(true)
  }, [load])

  const value = {
    data,
    loading,
    refreshing,
    error,
    cacheSource,
    cachedAt,
    refresh,
    retry,
    selectedTable,
    setSelectedTable,
    search,
    setSearch,
    showRelations,
    setShowRelations,
    previews,
    setPreviews,
  }

  return <SchemaContext.Provider value={value}>{children}</SchemaContext.Provider>
}

export function useSchema() {
  const ctx = useContext(SchemaContext)
  if (!ctx) throw new Error('useSchema must be used within SchemaProvider')
  return ctx
}
