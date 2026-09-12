import React, { useState } from 'react'
import { AuthProvider } from './context/AuthContext'
import { SearchProvider, useSearch } from './context/SearchContext'
import { PipelineProvider } from './context/PipelineContext'
import { BrowserRouter, Routes, Route, useNavigate } from './context/RouterContext'
import Navbar from './components/Navbar'
import AuthModal from './components/AuthModal'
import HomePage from './pages/HomePage'
import ResultsPage from './pages/ResultsPage'
import DashboardPage from './pages/DashboardPage'
import AgentPage from './pages/AgentPage'
import RagSection from './components/rag/RagSection'

function NavigationHeader({ onOpenAuth }) {
  const { clearSearch } = useSearch()
  const navigate = useNavigate()

  const handleResetSearch = () => {
    clearSearch()
    navigate('/')
  }

  return <Navbar onOpenAuth={onOpenAuth} onResetSearch={handleResetSearch} />
}

function MainApp() {
  const [authModalOpen, setAuthModalOpen] = useState(false)
  const [authModalMode, setAuthModalMode] = useState('login')

  return (
    <div className="app-layout">
      {/* Universal Top Navigation */}
      <NavigationHeader
        onOpenAuth={(mode) => {
          setAuthModalMode(mode)
          setAuthModalOpen(true)
        }}
      />

      {/* Dynamic Route Switching */}
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/results" element={<ResultsPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/agent" element={<AgentPage />} />
        <Route path="/rag" element={<RagSection />} />
        <Route path="*" element={<HomePage />} />
      </Routes>

      {/* Global Authentication Modal */}
      <AuthModal
        isOpen={authModalOpen}
        initialMode={authModalMode}
        onClose={() => setAuthModalOpen(false)}
      />
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <PipelineProvider>
          <SearchProvider>
            <MainApp />
          </SearchProvider>
        </PipelineProvider>
      </BrowserRouter>
    </AuthProvider>
  )
}
