import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { analyzeQuery, checkHealth } from '../api/analyst'

const ChatContext = createContext(null)

let messageId = 0
function nextId() {
  messageId += 1
  return messageId
}

export function ChatProvider({ children }) {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [apiOnline, setApiOnline] = useState(null)
  const [pendingClarification, setPendingClarification] = useState(null)
  const [draftInput, setDraftInput] = useState('')
  const pendingQueryRef = useRef('')

  useEffect(() => {
    checkHealth()
      .then(() => setApiOnline(true))
      .catch(() => setApiOnline(false))
  }, [])

  const appendMessage = useCallback((message) => {
    setMessages((prev) => [...prev, { id: nextId(), ...message }])
  }, [])

  const handleResponse = useCallback(
    (query, data) => {
      if (data.status === 'needs_clarification' && data.clarification?.options?.length) {
        const { parameter, options, message } = data.clarification
        pendingQueryRef.current = query
        setPendingClarification({
          query,
          parameter,
          options,
        })
        appendMessage({
          role: 'assistant',
          content: message || data.insight || 'Please select an option below.',
          status: data.status,
          clarification: data.clarification,
          traceId: data.trace_id,
        })
        return
      }

      setPendingClarification(null)
      pendingQueryRef.current = ''

      if (data.status === 'failed') {
        appendMessage({
          role: 'error',
          content: data.insight || data.error?.message || 'The request failed.',
          status: data.status,
          traceId: data.trace_id,
        })
        return
      }

      let content = data.insight || 'Analysis complete.'
      if (data.status === 'partial') {
        content = `[Partial result] ${content}`
      }
      if (data.entity_match_notes?.length) {
        content += `\n\nNote: ${data.entity_match_notes.join(' ')}`
      }

      appendMessage({
        role: 'assistant',
        content,
        status: data.status,
        traceId: data.trace_id,
        rowCount: data.row_count,
      })
    },
    [appendMessage],
  )

  const sendMessage = useCallback(
    async (text, resolvedFilters = {}) => {
      const query = text.trim()
      if (!query || loading) return

      appendMessage({ role: 'user', content: query })
      setLoading(true)

      try {
        const data = await analyzeQuery(query, resolvedFilters)
        handleResponse(query, data)
      } catch (err) {
        setPendingClarification(null)
        appendMessage({
          role: 'error',
          content: err instanceof Error ? err.message : 'Something went wrong.',
        })
      } finally {
        setLoading(false)
      }
    },
    [appendMessage, handleResponse, loading],
  )

  const selectClarificationOption = useCallback(
    async (option) => {
      if (!pendingClarification || loading) return

      const { query, parameter } = pendingClarification
      appendMessage({
        role: 'user',
        content: option.label,
      })
      setPendingClarification(null)
      setLoading(true)

      try {
        const data = await analyzeQuery(query, { [parameter]: option.value })
        handleResponse(query, data)
      } catch (err) {
        appendMessage({
          role: 'error',
          content: err instanceof Error ? err.message : 'Something went wrong.',
        })
      } finally {
        setLoading(false)
      }
    },
    [appendMessage, handleResponse, loading, pendingClarification],
  )

  const clearChat = useCallback(() => {
    setMessages([])
    setPendingClarification(null)
    setDraftInput('')
    pendingQueryRef.current = ''
  }, [])

  const value = {
    messages,
    loading,
    apiOnline,
    pendingClarification,
    draftInput,
    setDraftInput,
    sendMessage,
    selectClarificationOption,
    clearChat,
  }

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export function useChat() {
  const ctx = useContext(ChatContext)
  if (!ctx) throw new Error('useChat must be used within ChatProvider')
  return ctx
}
