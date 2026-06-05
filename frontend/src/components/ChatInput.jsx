import { useChat } from '../context/ChatContext'
import './ChatInput.css'

export default function ChatInput({ onSend, disabled, placeholder }) {
  const { draftInput, setDraftInput } = useChat()

  const submit = () => {
    const text = draftInput.trim()
    if (!text || disabled) return
    onSend(text)
    setDraftInput('')
  }

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className="chat-input-wrap">
      <form
        className="chat-input-form"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        <textarea
          className="chat-input"
          value={draftInput}
          onChange={(event) => setDraftInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          aria-label="Message"
        />
        <button type="submit" className="send-btn" disabled={disabled || !draftInput.trim()}>
          <span className="sr-only">Send</span>
          <svg viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M5 12h12M13 6l6 6-6 6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </form>
      <p className="input-hint">Enter to send · Shift+Enter for new line</p>
    </div>
  )
}
