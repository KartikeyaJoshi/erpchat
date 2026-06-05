import './MessageBubble.css'

function formatContent(text) {
  if (!text) return []
  return text.split('\n').filter(Boolean)
}

export default function MessageBubble({ message }) {
  const lines = formatContent(message.content)
  const isUser = message.role === 'user'
  const isError = message.role === 'error'

  return (
    <article
      className={`message ${isUser ? 'message-user' : isError ? 'message-error' : 'message-assistant'}`}
    >
      {!isUser && (
        <div className="message-avatar" aria-hidden>
          {isError ? '!' : 'A'}
        </div>
      )}
      <div className="message-body">
        <div className="message-meta">
          <span className="message-author">
            {isUser ? 'You' : isError ? 'Error' : 'Analyst'}
          </span>
          {message.status && !isUser && (
            <span className={`message-status status-${message.status}`}>
              {message.status.replace(/_/g, ' ')}
            </span>
          )}
        </div>
        <div className="message-content">
          {lines.map((line, index) => {
            const numbered = line.match(/^(\d+)\.\s+(.+)$/)
            if (numbered) {
              return (
                <p key={index} className="message-line message-numbered">
                  <span className="line-num">{numbered[1]}.</span>
                  {numbered[2]}
                </p>
              )
            }
            return (
              <p key={index} className="message-line">
                {line}
              </p>
            )
          })}
        </div>
        {message.rowCount != null && message.role === 'assistant' && message.status === 'success' && (
          <p className="message-footnote">{message.rowCount} row(s) returned</p>
        )}
      </div>
    </article>
  )
}
