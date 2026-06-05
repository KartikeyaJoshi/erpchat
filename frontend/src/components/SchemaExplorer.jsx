import { useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { fetchTablePreview } from '../api/schema'
import { useSchema } from '../context/SchemaContext'
import { readPreviewCache, writePreviewCache } from '../lib/schemaCache'
import './SchemaExplorer.css'

function formatCell(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  const text = String(value)
  return text.length > 80 ? `${text.slice(0, 77)}…` : text
}

function formatCachedTime(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function TableCard({ name, table, isSelected, onSelect }) {
  const fkEntries = table.foreign_keys ? Object.entries(table.foreign_keys) : []

  return (
    <motion.button
      type="button"
      className={`schema-table-card ${isSelected ? 'selected' : ''}`}
      onClick={() => onSelect(name)}
      layout
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.99 }}
    >
      <div className="schema-table-card-head">
        <span className="schema-table-name">{name}</span>
        <span className="schema-table-count">{table.columns.length} cols</span>
      </div>
      <div className="schema-table-meta-row">
        <span className="schema-row-count">{table.row_count?.toLocaleString() ?? 0} rows</span>
        {table.primary_key && (
          <span className="schema-table-pk">
            PK <code>{table.primary_key}</code>
          </span>
        )}
      </div>
      {fkEntries.length > 0 && (
        <div className="schema-table-fks">
          {fkEntries.slice(0, 2).map(([col, ref]) => (
            <span key={col} className="schema-fk-tag">
              {col} → {ref}
            </span>
          ))}
          {fkEntries.length > 2 && (
            <span className="schema-fk-more">+{fkEntries.length - 2} more</span>
          )}
        </div>
      )}
    </motion.button>
  )
}

function SampleDataTable({ rows, columns }) {
  if (!rows?.length) {
    return <p className="schema-empty-rows">No rows in this table yet.</p>
  }

  const colNames = columns?.length
    ? columns.map((c) => c.name)
    : Object.keys(rows[0] || {})

  return (
    <div className="schema-data-table-wrap">
      <table className="schema-data-table">
        <thead>
          <tr>
            {colNames.map((col) => (
              <th key={col}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {colNames.map((col) => (
                <td key={col} title={row[col] != null ? String(row[col]) : undefined}>
                  {formatCell(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TableDetail({ name, table, sampleRows, previewLoading, previewError }) {
  if (!table) return null

  const fkEntries = table.foreign_keys ? Object.entries(table.foreign_keys) : []
  const rows = sampleRows ?? table.sample_rows ?? []

  return (
    <motion.div
      className="schema-detail"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <div className="schema-detail-header">
        <h3 className="schema-detail-title">{name}</h3>
        <span className="schema-detail-rows">
          {table.row_count?.toLocaleString() ?? 0} live rows
        </span>
      </div>

      <div className="schema-detail-section">
        <h4 className="schema-detail-label">Columns</h4>
        <div className="schema-column-list">
          {table.columns.map((col) => (
            <span
              key={col.name}
              className={`schema-column-chip ${col.is_primary_key ? 'pk' : ''} ${col.foreign_key ? 'fk' : ''}`}
              title={col.foreign_key ? `→ ${col.foreign_key}` : col.data_type}
            >
              <span className="schema-col-name">{col.name}</span>
              <span className="schema-col-type">{col.udt_name || col.data_type}</span>
              {col.is_primary_key && <span className="schema-col-badge">PK</span>}
              {col.foreign_key && <span className="schema-col-badge">FK</span>}
            </span>
          ))}
        </div>
      </div>

      {fkEntries.length > 0 && (
        <div className="schema-detail-section">
          <h4 className="schema-detail-label">Relationships</h4>
          <ul className="schema-rel-list">
            {fkEntries.map(([col, ref]) => (
              <li key={col}>
                <code>{col}</code> references <code>{ref}</code>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="schema-detail-section">
        <h4 className="schema-detail-label">Live sample data</h4>
        {previewLoading && <p className="schema-sample-note">Loading sample rows…</p>}
        {previewError && <p className="schema-sample-note schema-sample-note--error">{previewError}</p>}
        {!previewLoading && !previewError && (
          <p className="schema-sample-note">Showing {rows.length} sample rows</p>
        )}
        <SampleDataTable rows={rows} columns={table.columns} />
      </div>
    </motion.div>
  )
}

export default function SchemaExplorer() {
  const {
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
  } = useSchema()
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState(null)

  const tableNames = useMemo(
    () => (data?.tables ? Object.keys(data.tables).sort() : []),
    [data],
  )

  const filteredTables = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return tableNames
    return tableNames.filter((name) => {
      const table = data.tables[name]
      if (name.includes(q)) return true
      return table.columns.some(
        (c) => c.name.includes(q) || c.data_type.includes(q),
      )
    })
  }, [search, tableNames, data])

  const activeTable = selectedTable && data?.tables?.[selectedTable]
    ? selectedTable
    : filteredTables[0] ?? null

  const activeTableData = activeTable ? data?.tables?.[activeTable] : null

  useEffect(() => {
    setPreviews({})
    setPreviewError(null)
  }, [data?.fetched_at])

  useEffect(() => {
    if (!activeTable) return

    const cached = readPreviewCache(activeTable)
    if (cached) {
      setPreviews((prev) => ({ ...prev, [activeTable]: cached }))
      setPreviewError(null)
      return
    }

    let cancelled = false
    setPreviewLoading(true)
    setPreviewError(null)

    fetchTablePreview(activeTable)
      .then((result) => {
        if (cancelled) return
        const rows = result.rows ?? []
        writePreviewCache(activeTable, rows)
        setPreviews((prev) => ({ ...prev, [activeTable]: rows }))
      })
      .catch((err) => {
        if (cancelled) return
        setPreviewError(err instanceof Error ? err.message : 'Failed to load preview')
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [activeTable])

  return (
    <div className="schema-explorer">
      <div className="schema-messages-bg" aria-hidden>
        <div className="schema-bg-orb schema-bg-orb--1" />
        <div className="schema-bg-orb schema-bg-orb--2" />
        <div className="schema-bg-grid" />
      </div>

      <div className="schema-explorer-inner">
        <header className="schema-header">
          <div className="schema-header-top">
            <h2 className="schema-title">Database Schema</h2>
            <span className="schema-live-pill">Live</span>
          </div>
          <div className="schema-header-actions">
            <div className="schema-meta-bar">
              {data && <span>{data.table_count} tables</span>}
              {data && <span>{data.database}</span>}
              {cachedAt && (
                <span className="schema-cache-info" title={`Source: ${cacheSource || 'unknown'}`}>
                  Cached {formatCachedTime(cachedAt)}
                </span>
              )}
            </div>
            <button
              type="button"
              className="schema-refresh-btn"
              onClick={refresh}
              disabled={loading || refreshing}
            >
              {refreshing ? 'Refreshing…' : 'Refresh from DB'}
            </button>
          </div>
        </header>

        {loading && !data && (
          <div className="schema-state schema-state--loading">
            <div className="schema-spinner" />
            <p>Loading schema…</p>
          </div>
        )}

        {error && !data && (
          <div className="schema-state schema-state--error">
            <p>{error}</p>
            <button type="button" className="schema-retry-btn" onClick={retry}>
              Retry
            </button>
          </div>
        )}

        {data && (
          <>
            <div className="schema-search-wrap">
              <svg className="schema-search-icon" viewBox="0 0 24 24" fill="none" aria-hidden>
                <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.75" />
                <path d="M16 16l4 4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
              </svg>
              <input
                type="search"
                className="schema-search"
                placeholder="Search tables or columns…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <div className="schema-body schema-body--page">
              <div className="schema-sidebar">
                <h3 className="schema-group-label">Tables</h3>
                <div className="schema-group-tables">
                  {filteredTables.map((tableName) => (
                    <TableCard
                      key={tableName}
                      name={tableName}
                      table={data.tables[tableName]}
                      isSelected={activeTable === tableName}
                      onSelect={setSelectedTable}
                    />
                  ))}
                  {filteredTables.length === 0 && (
                    <p className="schema-no-results">No tables match your search.</p>
                  )}
                </div>
              </div>

              <div className="schema-main">
                <AnimatePresence mode="wait">
                  {activeTableData ? (
                    <TableDetail
                      key={activeTable}
                      name={activeTable}
                      table={activeTableData}
                      sampleRows={previews[activeTable]}
                      previewLoading={previewLoading}
                      previewError={previewError}
                    />
                  ) : (
                    <div className="schema-state">No tables found in the public schema.</div>
                  )}
                </AnimatePresence>
              </div>
            </div>

            <footer className="schema-footer">
              <button
                type="button"
                className="schema-joins-toggle"
                onClick={() => setShowRelations((v) => !v)}
                aria-expanded={showRelations}
              >
                <span>Relationships ({data.relationships?.length ?? 0})</span>
                <svg
                  className={`schema-joins-chevron ${showRelations ? 'open' : ''}`}
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden
                >
                  <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
                </svg>
              </button>
              <AnimatePresence>
                {showRelations && (
                  <motion.ul
                    className="schema-joins-list"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25 }}
                  >
                    {(data.relationships ?? []).map((rel) => (
                      <li key={`${rel.from_table}-${rel.from_column}-${rel.to_table}`}>
                        <code>{rel.from_table}</code>
                        <span className="schema-join-arrow">.</span>
                        <code>{rel.from_column}</code>
                        <span className="schema-join-arrow">→</span>
                        <code>{rel.to_table}</code>
                        <span className="schema-join-arrow">.</span>
                        <code>{rel.to_column}</code>
                      </li>
                    ))}
                  </motion.ul>
                )}
              </AnimatePresence>
            </footer>
          </>
        )}
      </div>
    </div>
  )
}
