# Visual Product Search Engine & Multi-Agent Vision Gateway

An end-to-end multimodal Visual Product Search and Vision Gateway system capable of retrieving visually and semantically similar items across **44,000+ catalog products** in real time (<150 ms latency), with dedicated cross-module pipeline orchestration for multi-agent workflows.

Built with **FastAPI**, **OpenCLIP ViT-B-32**, **ResNet-50**, **FAISS IndexIDMap2**, **Dual-Database Layer (PostgreSQL / SQLite)**, and **React (Vite)**.

---

## 🌟 Key Features & Capabilities

- **Dual Embedding Models**: Seamlessly switch between **OpenCLIP ViT-B-32** (`laion2b_s34b_b79k`, 512-dim) and **ResNet-50** (2048-dim) per search request via the `model` parameter.
- **Fast In-Memory Vector Index**: FAISS `IndexIDMap2(IndexFlatIP)` indexing 44,119 searchable catalog items with <20 ms retrieval time.
- **Multi-Agent Pipeline Integration (Week 4)**: Standardized Vision Adapter (`process_vision_request`) communicating with a shared Supabase PostgreSQL instance (`pipeline_runs`, `assets`, `extracted_data`, `module_events`) for seamless RAG and agent handoffs.
- **Unified Gateway Engine (Week 5)**: Dedicated `/api/v1/gateway/run` and `/api/v1/gateway/run/{run_id}` endpoints enabling the central orchestrator to trigger visual similarity extraction, track execution traces, audit module events, and update pipeline run statuses to `vision_complete`.
- **Decoupled Database Architecture**: Unambiguous database resolution supporting:
  - Local SQLite fallback catalog (`data/catalog.db`)
  - Dedicated catalog PostgreSQL (`CATALOG_DATABASE_URL`)
  - Shared multi-agent Supabase PostgreSQL (`SHARED_DATABASE_URL`)
- **Resilient Image Serving & ORB Defense**: Embedded `Cross-Origin-Resource-Policy: cross-origin` headers preventing modern Chromium `ERR_BLOCKED_BY_ORB` failures, multi-directory disk fallback, and automated on-the-fly SVG placeholder generation for missing catalog assets.
- **User Authentication System**: JWT-like bearer token auth with PBKDF2-HMAC-SHA256 password hashing (100,000 iterations). Features signup, login, profile fetch, and a one-click demo login endpoint.
- **Catalog Browsing & Category Filtering**: Browse catalog categories with item counts and filter by article type or category name without requiring a query image.
- **Zero-Leakage Evaluation**: Strict separation of 44,119 catalog items, 100 validation queries, 200 clean test queries, and 200 messy test queries across 8 transformation types.
- **Modern Responsive Frontend**: React 18 + Vite SPA with drag-and-drop upload, quick-select categories, interactive model switching, top-K selection, and modal detail inspection.

---

## 🏛️ System Architecture

```text
====================================================================================================
1. DIRECT WEB & CLIENT SEARCH FLOW
====================================================================================================
[ React Frontend (Vite SPA) / Client ]
                  │
                  │  POST /search  or  POST /api/v1/search  (Multipart Form-Data / Query Params)
                  ▼
   [ FastAPI Backend (app.main / vision_router) ]
                  │
       ┌──────────┴──────────────────────────────────────┐
       ▼                                                 ▼
[ OpenCLIP ViT-B-32 ]                           [ ResNet-50 ]
(512-dim L2-normalized vector)                  (2048-dim embedding)
       │                                                 │
       ▼                                                 ▼
[ FAISS IndexIDMap2 ]                          [ FAISS IndexIDMap2 ]
  artifacts/faiss/clip.index                     artifacts/faiss/resnet.index
  (Top-K ID retrieval in <20 ms)
       │
       ▼
[ HSV Color Histogram Re-ranking ] (optional secondary scoring)
       │
       ▼
[ Catalog Database: SQLite / PostgreSQL ] ──> Order-preserving batch metadata lookup
       │
       ▼
[ JSON Search Response ] + [ ORB-Protected Image Delivery (/catalog-images/{filename}) ]


====================================================================================================
2. UNIFIED GATEWAY & MULTI-AGENT PIPELINE FLOW (Week 4 & Week 5)
====================================================================================================
[ Multi-Agent Orchestrator / Gateway ]
                  │
                  │  POST /api/v1/gateway/run  (run_id, image, top_k, model)
                  ▼
     [ FastAPI Gateway Endpoint ]
                  │
                  │ 1. Validate seeded run_id in pipeline_runs
                  │ 2. Invoke Vision Adapter (process_vision_request)
                  ▼
       [ Vision Adapter Pipeline ]
                  │
                  ├──> Vector embedding & FAISS Top-K candidate search
                  ├──> Catalog metadata resolution (product title, category, scores)
                  │
                  ▼
     [ Shared Supabase PostgreSQL ]
                  ├──> assets: Register query image asset with run_id
                  ├──> extracted_data: Save structured visual matches (module="vision")
                  ├──> module_events: Audit log (started, finished, duration_ms)
                  └──> pipeline_runs: Transition status to "vision_complete"
                  │
                  ▼
[ Handoff to RAG / Multi-Agent Synthesis ]
```

---

## 📁 Project Structure

```text
visual-product-search/
├── app/                               # Core backend application
│   ├── main.py                        # FastAPI entrypoint, middleware, lifespan manager
│   ├── vision_router.py               # Vision API router: search, catalog, gateway, images
│   ├── db/
│   │   ├── database.py                # Catalog DB abstraction (SQLite + dedicated PostgreSQL)
│   │   └── shared_database.py         # Shared multi-agent DB service (Supabase PostgreSQL)
│   ├── modules/
│   │   └── vision/
│   │       └── adapter.py             # Standardized vision processing adapter for agent pipelines
│   ├── schemas/
│   │   ├── auth.py                    # Auth request & response schemas
│   │   ├── gateway.py                 # Gateway run execution & detail schemas
│   │   ├── search.py                  # Search endpoint request/response models
│   │   └── vision_pipeline.py         # Standardized vision output & match schemas
│   └── services/
│       ├── auth_service.py            # Bearer token generation & PBKDF2 hashing
│       ├── clip_search_service.py     # OpenCLIP + FAISS search service
│       ├── resnet_search_service.py   # ResNet-50 + FAISS search service
│       ├── embedding_service.py       # OpenCLIP feature extraction
│       ├── resnet_embedding_service.py# ResNet-50 feature extraction
│       ├── reranking_service.py       # HSV color histogram re-ranking
│       └── search_service_registry.py # Lazy singleton search service cache
├── frontend/                          # React + Vite frontend application
│   ├── src/
│   │   ├── App.jsx                    # Root app component with providers & routing
│   │   ├── main.jsx                   # Vite entry point
│   │   ├── index.css                  # Design system, glassmorphism styling, animations
│   │   ├── components/                # Reusable UI components
│   │   │   ├── Navbar.jsx             # Navigation bar with auth & demo login
│   │   │   ├── AuthModal.jsx          # Login & registration modal
│   │   │   ├── ImageUploader.jsx      # Drag-and-drop file uploader
│   │   │   ├── SearchControls.jsx     # Model selection & Top-K slider
│   │   │   ├── SampleQueries.jsx      # Quick-select category cards
│   │   │   ├── ResultCard.jsx         # Product card with similarity score & find-similar
│   │   │   ├── ResultsWindowModal.jsx # Full-screen results inspector
│   │   │   └── ProductDetailModal.jsx # Detailed product metadata view
│   │   ├── pages/
│   │   │   ├── HomePage.jsx           # Landing page with uploader & controls
│   │   │   └── ResultsPage.jsx        # Ranked grid results page
│   │   ├── context/
│   │   │   ├── AuthContext.jsx        # Token persistence & user session
│   │   │   ├── RouterContext.jsx      # HTML5 history API navigation
│   │   │   └── SearchContext.jsx      # Search state & execution manager
│   │   └── services/
│   │       └── searchApi.js           # API client for search, categories, and images
│   ├── package.json
│   └── vite.config.js
├── artifacts/
│   ├── faiss/
│   │   ├── clip.index                 # Prebuilt OpenCLIP FAISS IndexIDMap2 index
│   │   └── resnet.index               # Prebuilt ResNet-50 FAISS IndexIDMap2 index
│   └── embeddings/
│       ├── clip_embeddings.npy        # 512-dim normalized vectors (44,119 items)
│       └── resnet_embeddings.npy      # 2048-dim normalized vectors (44,119 items)
├── data/
│   ├── catalog.db                     # Local SQLite fallback database (44,119 items)
│   └── images/                        # Catalog images
├── evaluation/                        # Evaluation dataset & benchmarks
│   ├── ground_truth.csv               # 200 clean test queries
│   ├── messy_query_manifest.csv       # 200 messy test queries (8 transformations)
│   ├── queries/                       # Query images
│   └── results/                       # Empirical benchmark results & metrics
├── docs/                              # Architecture documentation & contracts
│   ├── design-document.md             # Core system design document
│   ├── evaluation-report.md           # Benchmark and ablation reports
│   └── integration/
│       ├── vision-rag-contract.md     # Frozen Week 4 Vision → RAG interface contract
│       ├── shared-database-schema.md  # Multi-agent Supabase schema specification
│       └── frontend-shared-architecture.md # Blueprint for unified frontend integration
├── scripts/                           # Pipelines, migration, and verification suites
│   ├── verify_day1_gateway_vision.py  # 10-point Week 5 Gateway verification test suite
│   ├── verify_vision_process_endpoint.py # Week 4 adapter verification suite
│   ├── build_catalog_db.py            # Builds SQLite/PostgreSQL catalog tables
│   ├── build_clip_embeddings.py       # Offline OpenCLIP vector generation
│   ├── build_resnet_embeddings.py     # Offline ResNet vector generation
│   ├── build_faiss_index.py           # Builds FAISS vector index
│   └── run_final_evaluation.py        # Runs clean & messy benchmark matrices
├── requirements.txt
├── .env.example
└── README.md
```

---

## 📊 Empirical Evaluation Results (Clean & Messy Test Sets)

Evaluated across **200 clean test queries** and **200 realistic messy queries** (1,600 total evaluations across 8 transformation types: blur, crop, perspective, rotation, bright/dark lighting, contrast, and background padding):

| Evaluation Condition | Precision@1 | Precision@5 | Recall@5 | Hit@5 | MRR | Query Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CLIP Baseline — Clean Test** | **0.2850** | **0.1180** | **0.3608** | **0.4600** | **0.3626** | **141.7 ms** |
| **CLIP + Color Re-ranking — Clean Test** | **0.2850** | **0.1180** | **0.3608** | **0.4600** | **0.3635** | **138.7 ms** |
| **ResNet-50 Baseline — Clean Test** | 0.2350 | 0.0910 | 0.2691 | 0.3800 | 0.3023 | 225.7 ms |
| **CLIP Baseline — Messy Test** | **0.1300** | **0.0650** | **0.2075** | **0.2750** | **0.1895** | **138.8 ms** |
| **ResNet-50 Baseline — Messy Test** | 0.1300 | 0.0590 | 0.1760 | 0.2450 | 0.1769 | 229.5 ms |

---

## 🚀 Quick Start & How to Run

### 1. Prerequisites
- **Python 3.10+**
- **Node.js 18+** and **npm**

### 2. Setup Environment

```bash
# Clone the repository
git clone https://github.com/MuneebUrRehman545/visual-product-search.git
cd visual-product-search

# Setup Python virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Windows CMD:
.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

### 3. Start the Backend API Server

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
* **API Documentation (Swagger UI)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **Health Check Endpoint**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 4. Start the Frontend Development Server

```bash
cd frontend
npm install

# Run the Vite development server
npm run dev

# Note for Windows users if PowerShell script execution is restricted:
cmd.exe /c npm run dev
```
Open **[http://localhost:5173](http://localhost:5173)** in your browser.

---

## 🌐 Complete API Reference

### 1. Unified Gateway & Multi-Agent Integration Endpoints

#### `POST /api/v1/gateway/run`
Primary multi-agent orchestrator hook. Validates the seeded `run_id`, executes visual similarity retrieval via the Vision adapter, records database audit events, registers the asset, writes matches to `extracted_data`, and marks the run status as `vision_complete`.

* **Content-Type**: `multipart/form-data`
* **Form Parameters**:
  - `run_id` (*str, UUID, required*): The orchestrator-seeded execution trace ID.
  - `image` (*UploadFile, required*): The query image file (`image/jpeg`, `image/png`, `image/webp`).
  - `top_k` (*int, optional, default: 10*): Number of candidates to extract (1–50).
  - `model` (*str, optional, default: "clip"*): Embedding model (`"clip"` or `"resnet"`).

**Response (`200 OK`):**
```json
{
  "run_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "status": "vision_complete",
  "module": "vision",
  "total_matches": 10,
  "execution_time_ms": 142.5,
  "primary_match": {
    "product_id": 37779,
    "product_display_name": "John Players Men Check Green Shirt",
    "similarity_score": 0.9179,
    "image_url": "/catalog-images/37779.jpg"
  },
  "results": [ ... ]
}
```

#### `GET /api/v1/gateway/run/{run_id}` *(Alias: `/api/v1/runs/{run_id}`)*
Fetches complete execution trace details, asset IDs, audit event timestamps, and normalized vision extraction data for a given `run_id`.

#### `POST /api/v1/vision/process` *(Alias: `/vision/process`)*
Executes the Vision processing pipeline adhering to the frozen Week 4 Vision → RAG contract, persisting matches to the shared Supabase database.

---

### 2. Visual Similarity Search Endpoints

#### `POST /search` *(Aliases: `/api/search`, `/api/v1/search`, `/api/v1/vision/search`)*
Upload an image or specify an existing catalog filename to retrieve ranked visual matches.

* **Content-Type**: `multipart/form-data` (or query parameters)
* **Fields**:
  - `file` (*UploadFile, optional*): Uploaded query image.
  - `catalog_filename` (*str, optional*): Existing catalog image name (e.g. `37779.jpg`).
  - `top_k` (*int, default: 10*): Number of results to return.
  - `model` (*str, default: "clip"*): Model selection (`"clip"` or `"resnet"`).

**Response (`200 OK`):**
```json
{
  "query_filename": "query.jpg",
  "top_k": 5,
  "total_results": 5,
  "model_used": "OpenCLIP_ViT_B_32",
  "results": [
    {
      "rank": 1,
      "catalog_item_id": 7393,
      "product_id": 37779,
      "external_id": "37779",
      "filename": "37779.jpg",
      "product_display_name": "John Players Men Check Green Shirt",
      "category": "Apparel",
      "sub_category": "Topwear",
      "article_type": "Shirts",
      "base_colour": "Green",
      "gender": "Men",
      "season": "Summer",
      "usage": "Casual",
      "image_url": "/catalog-images/37779.jpg",
      "similarity_score": 0.9179
    }
  ]
}
```

---

### 3. Catalog Browsing & Image Endpoints

#### `GET /api/catalog/categories` *(Aliases: `/catalog/categories`, `/api/v1/catalog/categories`, `/categories`)*
Returns top categories with product counts and representative sample image URLs.

#### `GET /api/catalog/category/{category_name}` *(Aliases: `/catalog/category/{category_name}`, `/api/v1/catalog/category/{category_name}`)*
Returns product records filtered by category name or article type.

#### `GET /catalog-images/{filename}` *(Aliases: `/images/{filename}`, `/api/catalog-images/{filename}`)*
Serves catalog product images safely with path-traversal validation, cross-origin resource policy (`Cross-Origin-Resource-Policy: cross-origin`) headers to prevent `ERR_BLOCKED_BY_ORB`, and automatic on-the-fly SVG generation for any missing file.

---

### 4. Authentication Endpoints

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/api/auth/signup` | Register user (`email`, `username`, `password`) |
| `POST` | `/api/auth/login` | Log in and receive 7-day bearer token |
| `GET` | `/api/auth/me` | Fetch authenticated user profile (`Authorization: Bearer <token>`) |
| `GET` | `/api/auth/demo` | Instant one-click demo session without credentials |

---

## 🔒 Environment Variables & Database Resolution

Configuration is controlled via `.env` in the root directory:

```bash
# Application Environment (development / production)
APP_ENV=development

# ============================================================================
# Database Configuration & Resolution Precedence
# ============================================================================

# 1. Unified Gateway / Agent Database:
DATABASE_URL=postgresql://username:password@host:5432/agent_db?sslmode=require

# 2. Shared Cross-Module Pipeline Database (Supabase PostgreSQL):
# Used for pipeline_runs, assets, extracted_data, and module_events handoffs
SHARED_DATABASE_URL=postgresql://postgres.ref:pass@aws-0-region.pooler.supabase.com:5432/postgres?sslmode=require

# 3. Vision Catalog Database:
# - Default fallback: SQLite catalog database
DATABASE_PATH=data/catalog.db
# - Optional: Dedicated catalog PostgreSQL
# CATALOG_DATABASE_URL=postgresql://user:pass@host:5432/catalog_db?sslmode=require

# Storage Paths
CATALOG_IMAGES_DIR=data/images
EMBEDDINGS_DIR=artifacts/embeddings
FAISS_INDEX_DIR=artifacts/faiss

# CORS Whitelist (Comma-separated)
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Authentication Secret Key (HMAC-SHA256 signing)
AUTH_SECRET_KEY=change-me-in-production
```

### Database Resolution Logic
To prevent configuration collision when integrating with the Unified Gateway:
1. `CATALOG_DATABASE_URL` has **highest priority** for catalog item lookup.
2. If `SHARED_DATABASE_URL` is set and `CATALOG_DATABASE_URL` is omitted, the system ignores `DATABASE_URL` for catalog lookups and safely uses the local `DATABASE_PATH` SQLite database (`data/catalog.db`).
3. In standalone mode (when `SHARED_DATABASE_URL` is unset), `DATABASE_URL` serves as the catalog database.

---

## 🚀 Deployment & Multi-Agent Integration Status

| Service / Layer | Deployment Target | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Backend API & Gateway** | Local / Render | ✅ Active & Running | FastAPI listening on port `8000`, full Swagger UI and CORS |
| **Frontend Web App** | Local / Vercel | ✅ Active & Running | Vite SPA running on port `5173`, proxy & direct REST client |
| **Catalog Database** | SQLite / Neon / Supabase | ✅ Active (44,119 items) | SQLite local file `data/catalog.db` with order-preserving lookups |
| **Shared Multi-Agent DB** | Supabase PostgreSQL | ✅ Integrated | Tables `pipeline_runs`, `assets`, `extracted_data`, `module_events` |
| **Vector Index** | In-Memory FAISS | ✅ Loaded (<20 ms) | Loaded in RAM via `artifacts/faiss/clip.index` & `resnet.index` |

---

## ⚠️ Known Limitations & Design Findings

- **HSV Color Re-Ranking Ablation**: Color histogram re-ranking weight tuned to `0.0` on the 100-query validation set. As documented in our Week 3 evaluation, color histogram fusion provided negligible improvement over OpenCLIP representations alone.
- **Blur Sensitivity**: High blur levels reduce Hit@5 significantly (CLIP: 0.08, ResNet: 0.00), demonstrating that extreme blur destroys fine-grained fashion texture features.
- **CPU Inference Latency**: Running OpenCLIP and ResNet-50 on CPU yields ~120–170 ms per image query. Deploying with CUDA / TensorRT reduces latency below 30 ms.
- **Static FAISS Index**: The FAISS index operates in read-only mode during production serving; catalog updates require offline index rebuilding via `scripts/build_faiss_index.py`.

---

## 📈 Weekly Milestones & Implementation Progress

| Milestone | Key Deliverables | Status |
| :--- | :--- | :--- |
| **Week 1** | System architecture, OpenCLIP ViT-B-32 embeddings, FAISS IndexIDMap2 vector index, SQLite catalog database schema, offline pipeline scripts. | ✅ Complete |
| **Week 2** | FastAPI search backend, React/Vite web application, ResNet-50 baseline comparison model, 25-query evaluation set, model switching UI. | ✅ Complete |
| **Week 3** | HSV color re-ranking, 44,119-item leakage-free dataset split, 200 clean + 200 messy test queries (1,600 evaluations), auth system, catalog browse API. | ✅ Complete |
| **Week 4** | Frozen Vision → RAG interface contract, shared Supabase PostgreSQL schema (`pipeline_runs`, `assets`, `extracted_data`, `module_events`), `POST /api/v1/vision/process`, Vision Adapter. | ✅ Complete |
| **Week 5** | Unified Gateway integration (`POST /api/v1/gateway/run`, `GET /api/v1/gateway/run/{run_id}`), decoupled DB precedence, ORB defense image serving, and Day 1 verification suite. | ✅ Complete |

---

## 🧪 Verification Suites

The repository contains automated test suites to verify integration integrity:

```bash
# Verify Week 5 Day 1 Gateway integration & shared Supabase persistence
python scripts/verify_day1_gateway_vision.py

# Verify Week 4 Vision Adapter & process endpoint
python scripts/verify_vision_process_endpoint.py

# Run search engine benchmark evaluation
python scripts/run_final_evaluation.py
```

---

## 📄 License
This project is developed for educational, academic, and portfolio demonstration purposes.
