import Header from '../components/Header'
import ChatWindow from '../components/ChatWindow'
import { useChat } from '../hooks/useChat'
import '../App.css'

export default function ChatPage() {
  const {
    messages,
    loading,
    apiOnline,
    pendingClarification,
    sendMessage,
    selectClarificationOption,
    clearChat,
  } = useChat()

  return (
    <div className="app">
      <Header
        activePage="chat"
        apiOnline={apiOnline}
        onClear={clearChat}
        messageCount={messages.length}
      />
      <ChatWindow
        messages={messages}
        loading={loading}
        pendingClarification={pendingClarification}
        onSend={sendMessage}
        onSelectOption={selectClarificationOption}
        apiOnline={apiOnline}
      />
    </div>
  )
}
