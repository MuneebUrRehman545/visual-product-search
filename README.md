# Visual Product Search Engine

An end-to-end multimodal Visual Product Search system capable of retrieving visually and semantically similar items across **44,000+ catalog products** in real time (<150 ms latency).

Built with **FastAPI**, **OpenCLIP ViT-B-32**, **ResNet-50**, **FAISS IndexIDMap2**, **PostgreSQL / SQLite**, and **React (Vite)**.

---

## 🌟 Key Features & Highlights

- **Dual Embedding Models**: Switch between **OpenCLIP ViT-B-32** (`laion2b_s34b_b79k`, 512-dim) and **ResNet-50** (2048-dim) per search request via the `model` parameter.
- **Fast Vector Index**: FAISS `IndexIDMap2(IndexFlatIP)` indexing 44,119 searchable catalog items with <20 ms retrieval.
- **Dual-Database Layer**: Hosted PostgreSQL (Supabase / Neon) for production, plus local SQLite (`data/catalog.db`) fallback for local development.
- **Second-Stage Visual Re-ranking**: Modular 64-dimensional HSV color histogram score fusion.
- **User Authentication System**: JWT-like bearer token auth with PBKDF2-HMAC-SHA256 password hashing (100,000 iterations). Includes signup, login, profile fetch, and a one-click demo login endpoint.
- **Catalog Browsing API**: Browse products by top category or article type without a query image.
- **Zero-Leakage Evaluation**: Strict separation of 44,119 catalog items, 100 validation queries, 200 clean test queries, and 200 messy test queries across 8 transformation types.
- **Modern Responsive Frontend**: React + Vite SPA with drag-and-drop upload, quick-select sample categories, model switching, and ranked visual match cards.

---

## 🏛️ System Architecture

```text
[ React Frontend (Vite SPA) ]
             │
             │  HTTPS Multipart Image Upload / Catalog Filename
             ▼
[ FastAPI Backend (Render / Local) ]
             │
      ┌──────┴────────────────────────────────────────┐
      ▼                                               ▼
[ OpenCLIP ViT-B-32 ]                     [ ResNet-50 ]
(512-dim L2-normalized vector)            (2048-dim embedding)
      │                                               │
      ▼                                               ▼
[ FAISS IndexIDMap2 ]                    [ FAISS IndexIDMap2 ]
  clip.index                               resnet.index
  (Top-K candidates in <20 ms)
      │
      ▼
[ HSV Color Histogram Re-ranking ]  (optional, 64-dim)
      │
      ▼
[ PostgreSQL / SQLite — Order-Preserving Batch Metadata Lookup ]
      │
      ▼
[ JSON Search Response ]
```

---

## 📁 Project Structure

```text
visual-product-search/
├── app/                         # FastAPI backend application
│   ├── main.py                  # App entrypoint, all route handlers
│   ├── db/
│   │   └── database.py          # DB abstraction (PostgreSQL + SQLite)
│   ├── schemas/
│   │   ├── auth.py              # Pydantic auth request/response models
│   │   └── search.py            # Pydantic search request/response models
│   └── services/
│       ├── auth_service.py           # JWT token creation, PBKDF2 hashing
│       ├── clip_search_service.py    # OpenCLIP + FAISS search pipeline
│       ├── resnet_search_service.py  # ResNet-50 + FAISS search pipeline
│       ├── embedding_service.py      # OpenCLIP embedding generation
│       ├── resnet_embedding_service.py # ResNet-50 embedding generation
│       └── reranking_service.py      # HSV color histogram re-ranking
├── frontend/                    # React + Vite SPA
│   ├── src/
│   │   ├── App.jsx              # Root app with AuthProvider, BrowserRouter, SearchProvider
│   │   ├── main.jsx             # Vite entry point
│   │   ├── index.css            # Global design system & component styles
│   │   ├── components/          # Reusable UI components
│   │   │   ├── Navbar.jsx
│   │   │   ├── AuthModal.jsx
│   │   │   ├── ImageUploader.jsx
│   │   │   ├── SearchControls.jsx
│   │   │   ├── SampleQueries.jsx
│   │   │   ├── ResultsWindowModal.jsx
│   │   │   ├── ResultCard.jsx
│   │   │   └── ProductDetailModal.jsx
│   │   ├── pages/
│   │   │   ├── HomePage.jsx     # Upload dropzone + quick-select + controls
│   │   │   └── ResultsPage.jsx  # Ranked results grid + find-similar flow
│   │   ├── context/
│   │   │   ├── AuthContext.jsx   # Authentication state & token management
│   │   │   ├── SearchContext.jsx # Search state, execution, result caching
│   │   │   └── RouterContext.jsx # Custom HTML5 History API router
│   │   └── services/
│   │       └── searchApi.js     # API client: search, categories, image URL resolution
│   ├── package.json
│   ├── vite.config.js
│   └── .env.example
├── scripts/                     # Offline pipeline & evaluation scripts (35 total)
│   ├── build_catalog_db.py
│   ├── build_clip_embeddings.py
│   ├── build_resnet_embeddings.py
│   ├── build_faiss_index.py
│   ├── build_resnet_faiss_index.py
│   ├── build_color_features.py
│   ├── create_dataset_split.py
│   ├── validate_dataset.py
│   ├── import_production_embeddings.py
│   ├── tune_reranking.py
│   ├── run_final_evaluation.py
│   ├── evaluate_search.py
│   └── ...
├── artifacts/
│   ├── faiss/
│   │   ├── clip.index           # Production FAISS index (CLIP)
│   │   └── resnet.index         # Production FAISS index (ResNet-50)
│   └── embeddings/
│       ├── clip_embeddings.npy
│       └── resnet_embeddings.npy
├── data/
│   ├── catalog.db               # Local SQLite fallback database
│   └── images/                  # Catalog product images (44,119 items)
├── evaluation/                  # Ground-truth datasets & evaluation results
│   ├── README.md
│   ├── ground_truth.csv         # 200 clean test queries + ground truth
│   ├── messy_query_manifest.csv # 200 messy test queries (8 transform types)
│   └── queries/                 # Query image files
├── docs/                        # Design documents, evaluation reports
├── requirements.txt
└── .env.example
```

---

## 📊 Empirical Evaluation Results (Clean & Messy Test Sets)

Evaluated across **200 clean test queries** and **200 realistic messy queries** (1,600 total evaluations across 8 transformation types):

| Evaluation Condition | Precision@1 | Precision@5 | Recall@5 | Hit@5 | MRR | Query Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CLIP Baseline — Clean Test** | **0.2850** | **0.1180** | **0.3608** | **0.4600** | **0.3626** | **141.7 ms** |
| **CLIP + Color Re-ranking — Clean Test** | **0.2850** | **0.1180** | **0.3608** | **0.4600** | **0.3635** | **138.7 ms** |
| **ResNet-50 Baseline — Clean Test** | 0.2350 | 0.0910 | 0.2691 | 0.3800 | 0.3023 | 225.7 ms |
| **CLIP Baseline — Messy Test** | **0.1300** | **0.0650** | **0.2075** | **0.2750** | **0.1895** | **138.8 ms** |
| **ResNet-50 Baseline — Messy Test** | 0.1300 | 0.0590 | 0.1760 | 0.2450 | 0.1769 | 229.5 ms |

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites
- Python 3.10+
- Node.js 18+ and npm

### 2. Backend Setup
```bash
# 1. Clone repository
git clone https://github.com/MuneebUrRehman545/visual-product-search.git
cd visual-product-search

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate       # Linux / macOS
.venv\Scripts\Activate.ps1     # Windows PowerShell

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your DATABASE_URL, AUTH_SECRET_KEY, and other settings
```

### 3. Build Pipeline (Only Required When Rebuilding from Raw Data)
```bash
# Validate dataset images and metadata
python scripts/validate_dataset.py

# Create leakage-free catalog / validation / test splits
python scripts/create_dataset_split.py

# Build SQLite / PostgreSQL catalog table
python scripts/build_catalog_db.py

# Generate OpenCLIP 512-dim embeddings and FAISS index
python scripts/build_clip_embeddings.py
python scripts/build_faiss_index.py

# (Optional) Generate ResNet-50 2048-dim embeddings and FAISS index
python scripts/build_resnet_embeddings.py
python scripts/build_resnet_faiss_index.py

# Import production embeddings into the database
python scripts/import_production_embeddings.py \
  --embeddings-path artifacts/embeddings/clip_embeddings.npy \
  --model-name "open_clip:ViT-B-32:laion2b_s34b_b79k"

# Precompute HSV color features and tune re-ranking weights
python scripts/build_color_features.py
python scripts/tune_reranking.py

# Run the full final evaluation matrix
python scripts/run_final_evaluation.py
```

### 4. Start the Backend API Server
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
- **API Docs (Swagger)**: `http://127.0.0.1:8000/docs`
- **Health Check**: `http://127.0.0.1:8000/health`

### 5. Start the Frontend Development Server
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 🌐 Full API Reference

### `GET /health`
Returns system operational status, active database backend, model name, and catalog record count.

**Response:**
```json
{
  "status": "ok",
  "database": "postgresql",
  "catalog_count": 44119,
  "model": "OpenCLIP_ViT_B_32",
  "embedding_dimension": 512
}
```

---

### `POST /search` · `POST /api/v1/search`
Upload a query image or pass a catalog filename directly; returns the Top-K most visually similar products.

**Request (Multipart Form Data):**
| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `file` | File | — | Query image (`image/jpeg`, `image/png`, `image/webp`) |
| `catalog_filename` | string | — | Catalog image filename instead of an upload (e.g. `37779.jpg`) |
| `top_k` | int | `10` | Number of results to return (1–50) |
| `model` | string | `clip` | Embedding model: `clip` or `resnet` |

All fields also accepted as **query parameters**.

**Response:**
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

### `GET /catalog-images/{filename}`
Serves a catalog product image by filename. Protected against path traversal.

---

### `GET /api/catalog/categories?limit=8`
Returns the top `limit` categories with item counts and sample image URLs.

```json
{
  "total_categories": 8,
  "categories": [
    { "name": "Shirts", "count": 3128, "sample_image_url": "/catalog-images/37779.jpg" }
  ]
}
```

---

### `GET /api/catalog/category/{category_name}?limit=20`
Returns up to `limit` products for the given category or article type.

---

### Authentication Endpoints

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/api/auth/signup` | Register a new account (email, username, password) |
| `POST` | `/api/auth/login` | Authenticate and receive bearer token |
| `GET` | `/api/auth/me` | Fetch authenticated user profile (requires `Authorization: Bearer <token>`) |
| `GET` | `/api/auth/demo` | Instant one-click demo session (no credentials needed) |

**Signup / Login Request:**
```json
{ "email": "user@example.com", "username": "Alice", "password": "s3cur3pass" }
```

**Auth Response:**
```json
{
  "token": "<bearer-token>",
  "user": { "id": 1, "email": "user@example.com", "username": "Alice", "created_at": "..." },
  "message": "Account created successfully!"
}
```

> Token lifetime: **7 days**. Store in browser `localStorage` and pass as `Authorization: Bearer <token>` on authenticated requests.

---

## 🔒 Environment Variables

### Backend (`.env`)
| Variable | Description | Example |
| :--- | :--- | :--- |
| `DATABASE_URL` | PostgreSQL connection URI | `postgresql://user:pass@ep-host.neon.tech/catalog?sslmode=require` |
| `DATABASE_PATH` | Local SQLite path (fallback) | `data/catalog.db` |
| `CATALOG_IMAGES_DIR` | Path to catalog images | `data/images` |
| `EMBEDDINGS_DIR` | Path to `.npy` embedding files | `artifacts/embeddings` |
| `FAISS_INDEX_DIR` | Path to FAISS index files | `artifacts/faiss` |
| `ALLOWED_ORIGINS` | CORS whitelist (comma-separated) | `https://visual-product-search.vercel.app` |
| `AUTH_SECRET_KEY` | HMAC-SHA256 signing key for tokens | `change-me-in-production` |
| `APP_ENV` | Runtime environment | `development` / `production` |

### Frontend (`frontend/.env`)
| Variable | Description | Example |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | Backend base URL | `https://visual-product-search-api.onrender.com` |

---

## 🚀 Deployment

> **Status**: Deployment not completed as of Week 3. The backend was tested locally and is configured for deployment on **Render** (FastAPI) and the frontend is configured for **Vercel** (React/Vite). Production URLs will be added when deployed.

| Service | Provider | URL |
| :--- | :--- | :--- |
| Frontend | Vercel | *To be deployed* |
| Backend API | Render | *To be deployed* |
| Database | PostgreSQL (Supabase / Neon) | Configured via `DATABASE_URL` |

The frontend `.env.example` and backend `.env.example` are pre-configured with placeholder production URLs. Refer to the environment variables section above for required secrets.

---

## ⚠️ Known Limitations

- **Re-ranking did not improve Precision@K**: The HSV color histogram re-ranking (`color_weight = 0.0`) was tuned on the 100-query validation set and the optimal weight was zero — meaning color histogram re-ranking provided no measurable ranking improvement. The slight MRR gain (+0.0009) is within noise margin. This is documented honestly rather than over-stated.
- **Blur robustness is low**: CLIP scores only Hit@5 = 0.08 on blurred queries; ResNet scores 0.00. Heavy blur destroys fine-grained texture cues relied on by both models.
- **CPU-only inference**: Both embedding models run on CPU in the current setup. Embedding generation is the primary latency bottleneck (~120–170 ms per query). GPU deployment would significantly reduce this.
- **No persistent user data beyond tokens**: The auth system issues 7-day tokens; there is no persistent cart, wishlist, or user session beyond the token payload.
- **Static FAISS index**: The index must be rebuilt offline when catalog items are added or removed — there is no live index update mechanism.

---

## 🎬 Demo

Demo video: *To be added*

---

## 📈 Week 1–3 Progress Summary

| Week | Focus | Key Deliverables | Status |
| :--- | :--- | :--- | :--- |
| **Week 1** | Design, architecture, data ingestion foundation | System design doc, OpenCLIP embedding pipeline, FAISS IndexIDMap2, SQLite catalog DB, initial ingest scripts | ✅ Complete |
| **Week 2** | Visual similarity search, React frontend, evaluation dataset | FastAPI search API, React/Vite SPA with drag-and-drop upload, ResNet-50 comparison model, 25-query evaluation set, model switching | ✅ Complete |
| **Week 3** | Re-ranking, model comparison, full evaluation, documentation | HSV color re-ranking, 44,119-item leakage-free dataset split, 200 clean + 200 messy test queries, full evaluation matrix (8 conditions), auth system, catalog browse API, Week 3 README | ✅ Complete |

---

## 📄 License
This project is developed for educational and portfolio demonstration purposes.
