import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import MessageBubble from './MessageBubble'
import ClarificationPanel from './ClarificationPanel'
import TypingIndicator from './TypingIndicator'
import ChatInput from './ChatInput'
import './ChatWindow.css'

const FLOATING_ICONS = [
  {
    id: 'chart',
    className: 'chat-bg-icon chat-bg-icon--chart',
    delay: 0,
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <path d="M4 19V5a1 1 0 011-1h14a1 1 0 011 1v14M8 17v-4M12 17V9M16 17v-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'database',
    className: 'chat-bg-icon chat-bg-icon--database',
    delay: 0.4,
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <ellipse cx="12" cy="6" rx="8" ry="3" stroke="currentColor" strokeWidth="1.5" />
        <path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    ),
  },
  {
    id: 'users',
    className: 'chat-bg-icon chat-bg-icon--users',
    delay: 0.8,
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="9" cy="8" r="3" stroke="currentColor" strokeWidth="1.5" />
        <path d="M3 19c0-3.31 2.69-6 6-6s6 2.69 6 6M16 8a2.5 2.5 0 110 5M19 19c0-2.21-1.79-4-4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'inventory',
    className: 'chat-bg-icon chat-bg-icon--inventory',
    delay: 1.2,
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <path d="M3 9l9-5 9 5v10a1 1 0 01-1 1H4a1 1 0 01-1-1V9z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
        <path d="M9 22V12h6v10" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'currency',
    className: 'chat-bg-icon chat-bg-icon--currency',
    delay: 0.6,
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.5" />
        <path d="M12 8v8M9 10.5c0-1 1.5-1.5 3-1.5s3 .5 3 1.5-1.5 1.5-3 1.5-3 .5-3 1.5 1.5 1.5 3 1.5 3-.5 3-1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'report',
    className: 'chat-bg-icon chat-bg-icon--report',
    delay: 1,
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M9 14h6M9 18h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
]

const STARTERS = [
  'What is total revenue in 2026?',
  'What is the salary for Diya Sharma?',
  'What is stock at Mumbai Warehouse?',
  'Which customers have outstanding balance above 5 lakhs?',
]

export default function ChatWindow({
  messages,
  loading,
  pendingClarification,
  onSend,
  onSelectOption,
  apiOnline,
}) {
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, loading, pendingClarification])

  const showStarters = messages.length === 0 && !loading

  return (
    <div className="chat-window">
      <div className="chat-messages" ref={scrollRef}>
        <div className="chat-messages-bg" aria-hidden>
          <div className="chat-bg-orb chat-bg-orb--1" />
          <div className="chat-bg-orb chat-bg-orb--2" />
          <div className="chat-bg-orb chat-bg-orb--3" />
          <div className="chat-bg-grid" />
          <div className="chat-bg-rings">
            <div className="chat-bg-ring chat-bg-ring--1" />
            <div className="chat-bg-ring chat-bg-ring--2" />
          </div>
          {FLOATING_ICONS.map(({ id, className, delay, icon }) => (
            <motion.div
              key={id}
              className={className}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{
                opacity: 1,
                scale: 1,
                y: [0, -10, 0],
                rotate: [0, 3, -3, 0],
              }}
              transition={{
                opacity: { duration: 0.6, delay },
                scale: { duration: 0.6, delay },
                y: { duration: 5 + delay, repeat: Infinity, ease: 'easeInOut', delay },
                rotate: { duration: 7 + delay, repeat: Infinity, ease: 'easeInOut', delay },
              }}
            >
              {icon}
            </motion.div>
          ))}
        </div>

        <div className="chat-messages-content">
          {showStarters && (
            <section className="welcome">
              <div className="welcome-glow" aria-hidden />
              <span className="welcome-demo-badge">Live ERP data</span>
              <h2 className="welcome-title">Ask questions about the ERP dataset</h2>
              <p className="welcome-text">
                Browse live tables and sample rows on the{' '}
                <Link to="/schema" className="welcome-link">Schema page</Link>, then ask
                revenue, inventory, payroll, or customer questions in plain language.
              </p>
              <p className="welcome-disclaimer" role="note">
                <svg className="welcome-disclaimer-icon" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.75" />
                  <path d="M12 11v5M12 8h.01" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
                </svg>
                AI can make mistakes — verify important figures against the source data.
              </p>
              <div className="starters">
                {STARTERS.map((starter) => (
                  <button
                    key={starter}
                    type="button"
                    className="starter-chip"
                    onClick={() => onSend(starter)}
                    disabled={loading || apiOnline === false}
                  >
                    {starter}
                  </button>
                ))}
              </div>
            </section>
          )}

          <div className="message-list">
            {messages.map((message) => (
              <div key={message.id} className="message-wrap">
                <MessageBubble message={message} />
              </div>
            ))}
            {loading && <TypingIndicator />}
          </div>

          {pendingClarification && !loading && (
            <ClarificationPanel
              clarification={pendingClarification}
              onSelect={onSelectOption}
              disabled={loading}
            />
          )}
        </div>
      </div>

      <ChatInput
        onSend={onSend}
        disabled={loading || apiOnline === false}
        placeholder={
          apiOnline === false
            ? 'Start the API server to run the demo…'
            : pendingClarification
              ? 'Or type a unique detail to identify the record…'
              : 'Ask a business question…'
        }
      />
    </div>
  )
}
