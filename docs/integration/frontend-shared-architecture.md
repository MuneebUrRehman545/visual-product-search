# Unified Frontend Architecture & Porting Guide

**Target Base:** React 18 + Vite SPA (`frontend/`)  
**Collaborators:** Muneeb (Visual Product Search) & Moeez (Autonomous Research Agent)

---

## 1. Overview & Decision Context

We have confirmed using **Vite + React** (located in `frontend/`) as the single unified frontend base for the entire system instead of maintaining a separate Next.js shell.

Both capabilities will live under a cohesive single-page application:
1. **Visual Product Search:** Image upload, vector similarity search, multi-model evaluation (CLIP / ResNet), catalog browsing, and "Find Similar" visual queries.
2. **Autonomous Research Agent:** Goal dispatch, live WebSocket trace stream, dynamic step execution, replanning feedback, and markdown report view.

---

## 2. Existing Frontend Folder Structure

The current codebase is organized cleanly as follows:

```text
frontend/
├── index.html                  # HTML entry with viewport & Inter font
├── vite.config.js              # Vite configuration with React plugin
├── package.json                # Dependencies: react, react-dom, @vitejs/plugin-react, vite
├── .env.example                # VITE_API_BASE_URL configuration
└── src/
    ├── main.jsx                # React root mount
    ├── App.jsx                 # Top-level shell wrapping providers & routes
    ├── index.css               # Unified CSS design system & component styles
    ├── components/             # Reusable UI components
    │   ├── Navbar.jsx          # Top navigation bar with logo, stats pill, and auth controls
    │   ├── AuthModal.jsx       # Login, signup, and demo guest authentication modal
    │   ├── ImageUploader.jsx   # Drag-and-drop file dropzone with preview
    │   ├── SearchControls.jsx  # Model selector (CLIP/ResNet), top-K slider, trigger button
    │   ├── SampleQueries.jsx   # Quick-select category tiles
    │   ├── ResultCard.jsx      # Product result card with metadata & similarity score
    │   ├── ResultsWindowModal.jsx # Ranked results overlay
    │   ├── ProductDetailModal.jsx # Detail lightbox
    │   └── SearchResults.jsx   # Results container wrapper
    ├── context/                # Global state providers
    │   ├── AuthContext.jsx     # User session, JWT tokens, login/logout actions
    │   ├── SearchContext.jsx   # Visual search state, query preview, results cache
    │   └── RouterContext.jsx   # Custom HTML5 History API routing (BrowserRouter, Routes, Route, Link, useNavigate, useLocation)
    ├── pages/                  # Page-level route views
    │   ├── HomePage.jsx        # Visual search home screen (dropzone + category presets)
    │   └── ResultsPage.jsx     # Visual search ranked results view
    └── services/               # Backend communication
        └── searchApi.js        # REST client with dynamic LAN/localhost IP resolution
```

---

## 3. Target Shared Architecture

To integrate Moeez's WebSocket client and Agent Dashboard without conflict, we structure the directories into domain-focused submodules:

```text
frontend/src/
├── main.jsx
├── App.jsx                     # Shared App Shell wrapping all context providers
├── index.css                   # Global styles & design system
├── components/
│   ├── common/                 # Universal cross-cutting components
│   │   ├── Navbar.jsx          # Unified Top Navigation (Switch between Search & Agent)
│   │   ├── AuthModal.jsx       # Authentication modal
│   │   └── StatusBadge.jsx     # Reusable status pill for live stream & pipeline status
│   ├── vision/                 # Visual Product Search components (Muneeb)
│   │   ├── ImageUploader.jsx
│   │   ├── SearchControls.jsx
│   │   ├── SampleQueries.jsx
│   │   ├── ResultCard.jsx
│   │   ├── ProductDetailModal.jsx
│   │   └── ResultsWindowModal.jsx
│   └── agent/                  # Agent Dashboard components (Moeez)
│       ├── TraceFeed.jsx       # Live WebSocket trace events list & live progress
│       ├── PlanStatusView.jsx  # Multi-step plan execution overview
│       └── ReportView.jsx      # Final markdown research report viewer
├── context/
│   ├── AuthContext.jsx         # Global user session & JWT auth
│   ├── RouterContext.jsx       # Client-side router (with param support: /agent/runs/:id)
│   ├── SearchContext.jsx       # Visual search state (Muneeb)
│   └── AgentContext.jsx        # Agent state & WebSocket stream management (Moeez)
├── pages/
│   ├── vision/
│   │   ├── HomePage.jsx        # Visual search home (path: "/")
│   │   └── ResultsPage.jsx     # Visual search results (path: "/results")
│   └── agent/
│       ├── AgentHomePage.jsx   # Agent goal creation & launch (path: "/agent")
│       ├── AgentRunPage.jsx    # Live WebSocket trace & report view (path: "/agent/runs/:id")
│       └── AgentHistoryPage.jsx # Run history archive (path: "/agent/history")
└── services/
    ├── searchApi.js            # Visual search REST API client
    └── agentApi.js             # Agent REST API client + WebSocket URL builder
```

---

## 4. Key Architectural Placements

### 4.1. Shared Shell (`src/App.jsx`)
The shared shell establishes the provider hierarchy and defines top-level routes:

```jsx
import React, { useState } from 'react'
import { AuthProvider } from './context/AuthContext'
import { BrowserRouter, Routes, Route } from './context/RouterContext'
import { SearchProvider } from './context/SearchContext'
import { AgentProvider } from './context/AgentContext'

import Navbar from './components/common/Navbar'
import AuthModal from './components/common/AuthModal'

// Vision Pages
import HomePage from './pages/vision/HomePage'
import ResultsPage from './pages/vision/ResultsPage'

// Agent Pages
import AgentHomePage from './pages/agent/AgentHomePage'
import AgentRunPage from './pages/agent/AgentRunPage'
import AgentHistoryPage from './pages/agent/AgentHistoryPage'

function MainApp() {
  const [authModalOpen, setAuthModalOpen] = useState(false)
  const [authModalMode, setAuthModalMode] = useState('login')

  return (
    <div className="app-layout">
      {/* Universal Top Navigation Header */}
      <Navbar onOpenAuth={(mode) => {
        setAuthModalMode(mode)
        setAuthModalOpen(true)
      }} />

      {/* Unified Route Definitions */}
      <main className="main-content">
        <Routes>
          {/* Vision Routes */}
          <Route path="/" element={<HomePage />} />
          <Route path="/results" element={<ResultsPage />} />

          {/* Agent Routes */}
          <Route path="/agent" element={<AgentHomePage />} />
          <Route path="/agent/history" element={<AgentHistoryPage />} />
          <Route path="/agent/runs/:id" element={<AgentRunPage />} />

          {/* Default Fallback */}
          <Route path="*" element={<HomePage />} />
        </Routes>
      </main>

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
        <SearchProvider>
          <AgentProvider>
            <MainApp />
          </AgentProvider>
        </SearchProvider>
      </BrowserRouter>
    </AuthProvider>
  )
}
```

---

### 4.2. Universal Navigation (`src/components/common/Navbar.jsx`)

The top bar provides seamless switching between the two core experiences:

```jsx
<header className="navbar">
  <div className="navbar-container">
    {/* Brand / Logo */}
    <Link to="/" className="navbar-brand">
      <div className="brand-icon-wrapper">...</div>
      <div className="brand-text">
        <span className="brand-title">Multimodal Studio</span>
        <span className="brand-badge">v2.0</span>
      </div>
    </Link>

    {/* Module Navigation Tabs */}
    <nav className="nav-module-tabs">
      <Link
        to="/"
        className={`nav-tab ${!pathname.startsWith('/agent') ? 'active' : ''}`}
      >
        Visual Search
      </Link>
      <Link
        to="/agent"
        className={`nav-tab ${pathname.startsWith('/agent') ? 'active' : ''}`}
      >
        Research Agent
      </Link>
      {pathname.startsWith('/agent') && (
        <Link
          to="/agent/history"
          className={`nav-sub-tab ${pathname === '/agent/history' ? 'active' : ''}`}
        >
          History
        </Link>
      )}
    </nav>

    {/* Live Status Indicators */}
    <div className="catalog-status-pill">
      {!pathname.startsWith('/agent') ? (
        <>
          <span className="pulse-dot"></span>
          <span className="pill-text">44,119 Products Indexed</span>
        </>
      ) : (
        <AgentStreamStatusPill />
      )}
    </div>

    {/* Auth / User Menu */}
    <div className="navbar-actions">...</div>
  </div>
</header>
```

---

### 4.3. State Store (`src/context/AgentContext.jsx`)

Moeez's agent logic (run creation, WebSocket streaming, trace event reduction) lives in a dedicated `AgentProvider` mirroring Muneeb's `SearchContext.jsx`:

```jsx
import React, { createContext, useContext, useState, useCallback, useRef } from 'react'
import { createRun, getRun, getWebSocketUrl } from '../services/agentApi'

const AgentContext = createContext(null)

export function AgentProvider({ children }) {
  const [currentRun, setCurrentRun] = useState(null)
  const [traceEvents, setTraceEvents] = useState([])
  const [connectionStatus, setConnectionStatus] = useState('idle') // 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'closed'
  const [activePlan, setActivePlan] = useState(null)
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const wsRef = useRef(null)

  // Start a new research run
  const startRun = useCallback(async (goalText) => {
    setLoading(true)
    setError(null)
    try {
      const run = await createRun(goalText)
      setCurrentRun(run)
      return run
    } catch (err) {
      setError(err.message || 'Failed to initialize agent run')
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  // Connect WebSocket stream for a run
  const connectStream = useCallback((runId) => {
    if (wsRef.current) {
      wsRef.current.close()
    }

    setConnectionStatus('connecting')
    const wsUrl = getWebSocketUrl(runId)
    const socket = new WebSocket(wsUrl)
    wsRef.current = socket

    socket.onopen = () => {
      setConnectionStatus('connected')
    }

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        // Reduce incoming WebSocket events:
        // 'catch_up', 'plan_created', 'step_started', 'tool_call_started',
        // 'tool_call_result', 'observation_made', 'replan_triggered',
        // 'step_completed', 'report_ready', 'run_completed', 'run_failed'
        setTraceEvents((prev) => [...prev, payload])
        if (payload.type === 'report_ready' || payload.report) {
          setReport(payload.report || payload)
        }
      } catch (err) {
        console.error('Error parsing WebSocket message:', err)
      }
    }

    socket.onclose = () => {
      setConnectionStatus('closed')
    }

    socket.onerror = () => {
      setConnectionStatus('closed')
    }
  }, [])

  const disconnectStream = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setConnectionStatus('closed')
  }, [])

  const value = {
    currentRun,
    setCurrentRun,
    traceEvents,
    setTraceEvents,
    connectionStatus,
    activePlan,
    report,
    loading,
    error,
    startRun,
    connectStream,
    disconnectStream,
  }

  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>
}

export function useAgent() {
  const context = useContext(AgentContext)
  if (!context) {
    throw new Error('useAgent must be used within an AgentProvider')
  }
  return context
}
```

---

## 5. Porting Guide for Moeez's Next.js Code

| Moeez's Next.js Artifact | Vite / Shared Placement | Notes |
| :--- | :--- | :--- |
| `lib/api.ts` | `src/services/agentApi.js` | Replace `process.env.NEXT_PUBLIC_BACKEND_URL` with `import.meta.env.VITE_API_BASE_URL`. Export `createRun`, `getRun`, `getRuns`, `getWebSocketUrl`. |
| `app/page.tsx` | `src/pages/agent/AgentHomePage.jsx` | Change `useRouter()` to `useNavigate()`. Use `startRun()` from `useAgent()`. |
| `app/runs/[id]/page.tsx` | `src/pages/agent/AgentRunPage.jsx` | Extract `id` from route params or `useLocation()`. Use `connectStream(id)` from `useAgent()`. |
| `app/history/page.tsx` | `src/pages/agent/AgentHistoryPage.jsx` | List past runs, navigate to `/agent/runs/${id}` on click. |
| `components/TraceFeed.tsx` | `src/components/agent/TraceFeed.jsx` | Clean JSX component. Render step-by-step trace events. |
| `components/PlanStatusView.tsx` | `src/components/agent/PlanStatusView.jsx` | Visual step cards (pending, running, complete, failed, skipped). |
| `components/ReportView.tsx` | `src/components/agent/ReportView.jsx` | Markdown report display with export / copy buttons. |
| `components/StatusBadge.tsx` | `src/components/common/StatusBadge.jsx` | Reusable pill for status indicators. |

---

## 6. Route Parameter Handling

If retaining `RouterContext.jsx`, simple regex matching handles dynamic routes like `/agent/runs/:id`:

```javascript
// In RouterContext.jsx
export function useParams() {
  const { pathname } = useLocation()
  const runMatch = pathname.match(/^\/agent\/runs\/([^/]+)/)
  if (runMatch) {
    return { id: runMatch[1] }
  }
  return {}
}
```

*(Alternatively, installing `react-router-dom` (`npm install react-router-dom`) is a standard 1-step upgrade if standard route params and nesting are preferred).*

---

## 7. Git Remote & Branch Availability

The current frontend state has been synchronized across all branches and remotes:
- `origin/frontend`
- `moeez/frontend`
- `origin/integration/week5`
- `moeez/integration/week5`
- `moeez/muneeb/week5-vision`

To pull and start porting:
```bash
git fetch --all
git checkout frontend  # or checkout -b frontend origin/frontend
cd frontend
npm install
npm run dev
```
