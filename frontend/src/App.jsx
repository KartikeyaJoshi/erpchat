import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { ChatProvider } from './context/ChatContext'
import { SchemaProvider } from './context/SchemaContext'
import { ThemeProvider } from './context/ThemeContext'
import LandingPage from './pages/LandingPage'
import ChatPage from './pages/ChatPage'
import SchemaPage from './pages/SchemaPage'

function App() {
  return (
    <ThemeProvider>
      <ChatProvider>
        <SchemaProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/schema" element={<SchemaPage />} />
            <Route path="/chat" element={<ChatPage />} />
          </Routes>
        </BrowserRouter>
        </SchemaProvider>
      </ChatProvider>
    </ThemeProvider>
  )
}

export default App
