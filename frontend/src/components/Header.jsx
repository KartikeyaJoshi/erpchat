import { Link, useLocation } from 'react-router-dom'
import { isApiConfigured, getApiBaseUrl } from '../api/analyst'
import ThemeToggle from './ThemeToggle'
import './Header.css'

export default function Header({
  apiOnline,
  onClear,
  messageCount = 0,
  activePage,
}) {
  const location = useLocation()
  const page = activePage ?? (location.pathname.startsWith('/schema') ? 'schema' : 'chat')
  const apiConfigured = isApiConfigured()
  const apiStatusTitle =
    apiOnline === true
      ? `API connected (${getApiBaseUrl()})`
      : !apiConfigured
        ? 'API URL missing — set VITE_API_BASE_URL on Vercel and redeploy'
        : 'API offline — check Render service and FRONTEND_URL CORS setting'

  return (
    <header className="header">
      <div className="header-brand">
        <Link to="/" className="header-logo" aria-label="Back to home">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path
              d="M4 19V5a1 1 0 011-1h14a1 1 0 011 1v14M8 17v-4M12 17V9M16 17v-6"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
            />
          </svg>
        </Link>
        <div>
          <div className="header-title-row">
            <h1 className="header-title">ERPChat</h1>
            <span className="header-prototype-pill">Prototype</span>
          </div>
          <p className="header-subtitle">Natural-language analyst over live ERP data</p>
        </div>
      </div>
      <div className="header-actions">
        <nav className="header-nav" aria-label="App sections">
          <Link
            to="/schema"
            className={`header-nav-link ${page === 'schema' ? 'active' : ''}`}
          >
            Schema
          </Link>
          <Link
            to="/chat"
            className={`header-nav-link ${page === 'chat' ? 'active' : ''}`}
          >
            Chat
          </Link>
        </nav>
        <ThemeToggle />
        {apiOnline !== undefined && (
          <span
            className={`status-pill ${apiOnline === true ? 'online' : apiOnline === false ? 'offline' : 'unknown'}`}
            title={apiStatusTitle}
          >
            <span className="status-dot" />
            {apiOnline === true ? 'Connected' : apiOnline === false ? 'Offline' : 'Checking…'}
          </span>
        )}
        {messageCount > 0 && onClear && (
          <button type="button" className="btn-ghost" onClick={onClear}>
            New chat
          </button>
        )}
      </div>
    </header>
  )
}
