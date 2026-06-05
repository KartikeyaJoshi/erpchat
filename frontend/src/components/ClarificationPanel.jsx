import './ClarificationPanel.css'

export default function ClarificationPanel({ clarification, onSelect, disabled }) {
  if (!clarification?.options?.length) return null

  return (
    <div className="clarification-panel" role="group" aria-label="Select a matching record">
      <p className="clarification-label">Choose one:</p>
      <div className="clarification-options">
        {clarification.options.map((option) => (
          <button
            key={option.value}
            type="button"
            className="clarification-option"
            onClick={() => onSelect(option)}
            disabled={disabled}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}
