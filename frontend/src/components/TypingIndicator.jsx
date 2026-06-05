import './TypingIndicator.css'

export default function TypingIndicator() {
  return (
    <div className="typing" aria-live="polite" aria-label="Analyzing">
      <div className="typing-avatar" aria-hidden>
        A
      </div>
      <div className="typing-bubble">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
    </div>
  )
}
