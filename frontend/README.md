# Visual Product Search — Frontend

React + Vite SPA for the Visual Product Search Engine. Provides drag-and-drop image upload, quick-select category browsing, dual-model search controls, and a rich ranked-results experience.

## Tech Stack

| Layer | Technology |
| :--- | :--- |
| Framework | React 18 |
| Bundler | Vite 5 |
| Routing | Custom HTML5 History API router (`RouterContext.jsx`) |
| State | React Context API (`AuthContext`, `SearchContext`) |
| Styling | Vanilla CSS (`index.css`) |
| API Client | Fetch API (`searchApi.js`) |

## Project Structure

```text
frontend/
├── index.html
├── vite.config.js
├── package.json
├── .env.example
└── src/
    ├── main.jsx              # Vite entry point
    ├── App.jsx               # Root: AuthProvider → BrowserRouter → SearchProvider → MainApp
    ├── index.css             # Global design system, tokens, component styles
    ├── components/
    │   ├── Navbar.jsx              # Top navigation bar with auth controls
    │   ├── AuthModal.jsx           # Login / Signup modal
    │   ├── ImageUploader.jsx       # Drag-and-drop image upload dropzone
    │   ├── SearchControls.jsx      # Model selector, top-K slider, search button
    │   ├── SampleQueries.jsx       # Quick-select category tiles (live catalog browse)
    │   ├── ResultsWindowModal.jsx  # Ranked results overlay/modal
    │   ├── ResultCard.jsx          # Individual search result product card
    │   ├── ProductDetailModal.jsx  # Full product detail lightbox
    │   └── SearchResults.jsx       # Results container wrapper
    ├── pages/
    │   ├── HomePage.jsx      # Upload dropzone + quick-select categories + controls
    │   └── ResultsPage.jsx   # Ranked results grid with find-similar & detail flows
    ├── context/
    │   ├── AuthContext.jsx   # Auth state: user, token, login/logout/signup actions
    │   ├── SearchContext.jsx # Search state: file, results, loading, executeSearch()
    │   └── RouterContext.jsx # BrowserRouter, Routes, Route, Link, useNavigate, useLocation
    └── services/
        └── searchApi.js      # API client: searchProducts(), fetchTopCategories(), fetchCategoryProducts(), getCatalogImageUrl()
```

## Environment Variables

Create a `frontend/.env` file (copy from `.env.example`):

```env
# Backend API Base URL
# Leave blank to auto-detect from window.location.hostname (LAN-compatible)
# For production: set to your hosted FastAPI backend URL
VITE_API_BASE_URL=http://127.0.0.1:8000
```

When `VITE_API_BASE_URL` is not set, the frontend automatically resolves the backend URL from the browser's current hostname (e.g. `http://192.168.1.x:8000`), enabling seamless LAN device access.

## Scripts

```bash
# Install dependencies
npm install

# Start development server (http://localhost:5173)
npm run dev

# Build production bundle
npm run build

# Preview production build locally
npm run preview
```

## Key Behaviors

### Search Flow
1. User uploads an image via drag-and-drop **or** clicks a quick-select category tile.
2. `SearchContext.executeSearch()` calls `searchApi.searchProducts()` with the image file or catalog filename, `top_k`, and `model` parameters.
3. Results are stored in `SearchContext` and the router navigates to `/results`.
4. `ResultsPage` renders ranked product cards with similarity scores.
5. Any result card can be used as a new "Find Similar" query.

### Authentication
- `AuthContext` manages the bearer token in `localStorage`.
- `AuthModal` provides login, signup, and guest-demo flows.
- Demo login (`GET /api/auth/demo`) creates an instant session without credentials.
- Tokens expire after **7 days**; the context automatically clears stale tokens.

### API Base URL Resolution (LAN Support)
`searchApi.getApiBaseUrl()` resolves in order:
1. `VITE_API_BASE_URL` environment variable (Vite build-time or runtime)
2. `window.location.hostname` → `http://<hostname>:8000` (auto LAN detection)
3. Fallback: `http://127.0.0.1:8000`

## Unified Team Architecture (Week 5)

For details on integrating the Autonomous Research Agent (WebSocket live trace, step execution, replanning, and markdown reports) into this Vite base, see the full architectural blueprint:
👉 [`docs/integration/frontend-shared-architecture.md`](../docs/integration/frontend-shared-architecture.md)
