# Week 6 Day 2 — Task 3: Muneeb Vision Deployment Smoke Test

**Role:** Vision / Image-Intake Module Owner (Muneeb)  
**Date:** September 12, 2026  
**Status:** **BLOCKED**  

---

## Executive Summary

This smoke test report verifies the deployment readiness and remote operational status of the Vision/Image-Intake portion of the unified pipeline.

Per the smoke test protocol:
- **Step 1:** The tester must read current environment configuration/documentation to identify deployed frontend, unified backend, Vision routes, and catalog endpoints without inventing URLs. If missing from project configuration/documentation, it must be reported as a **BLOCKER**.
- **Step 6 & 8:** The test must not substitute `localhost`, local backend, local database, or local FAISS index. If requests target `localhost` or if no deployed cloud host exists, the test must be marked **BLOCKED** or **FAIL**.

An exhaustive audit of the workspace configuration, `.env` files, documentation, and live remote endpoints was conducted. While the unified pipeline (`backend/app/gateway/main.py` and `frontend/`) is verified and functional locally, **the deployed unified frontend and deployed unified backend hosting the integrated Vision module are not yet provisioned in a public cloud environment**.

---

## STEP 1 — Identify Deployed Services

| Configuration Key / Service | Source Location | Discovered Value / Reference | Live Network Probe Result | Finding |
| :--- | :--- | :--- | :--- | :--- |
| **Deployed Frontend URL** | `frontend/.env`<br>`backend/app/modules/agent/README.md` | `https://research-agent-five-delta.vercel.app/` | **HTTP 200 OK**<br>Serves `<title>Autonomous Research Agent</title>` | **Blocker / Mismatch:** Serves Moeez's standalone agent UI (Week 4 Phase 19). It does **not** contain the unified Vite frontend, the Visual Search UI, or an image upload dropzone. |
| **Deployed Unified Backend URL** | `frontend/.env.example`<br>`backend/app/modules/agent/README.md` | `https://visual-product-search-api.onrender.com`<br>`https://research-agent-rpkp.onrender.com` | `visual-product-search-api`: **HTTP 503 Service Unavailable**<br>`research-agent-rpkp`: **HTTP 200 OK** | **Blocker / Unprovisioned:** `visual-product-search-api` is unprovisioned. `research-agent-rpkp` is active, but inspecting its OpenAPI schema confirms it only mounts `/health`, `/runs`, `/runs/{run_id}`, `/runs/{run_id}/steps`, and `/runs/{run_id}/report`. It does **not** host the unified gateway or Vision routes. |
| **Configured Vision API Route** | `app/vision_router.py`<br>`backend/app/gateway/main.py` | `POST /search`<br>`POST /api/v1/search`<br>`POST /api/v1/vision/process`<br>`GET /api/v1/vision/health` | Fully implemented in repository and verified locally | Routes defined and functional on the unified gateway. |
| **Configured Catalog/Image Endpoint** | `app/vision_router.py`<br>`backend/app/gateway/main.py` | `GET /catalog-images/{filename}`<br>`GET /api/v1/catalog/images/{image_name}` | Fully implemented in repository with SVG fallback | Configured on unified gateway. |

---

## STEP 2 — Verify Deployed Frontend

- **Target Inspected:** `https://research-agent-five-delta.vercel.app/`
- **Application Load:** Successfully loads (HTTP 200), rendering a dark-themed Next.js dashboard.
- **Vision / Intake Section Visibility:** **Not present**. The loaded frontend contains goal input fields ("What was the average annual rainfall in Tokyo...", "What are the latest breakthroughs in solid-state battery technology...").
- **Upload Control:** **Not present**.
- **Assessment:** The team's unified frontend (`frontend/` React 18 / Vite SPA) has not been deployed to Vercel.

---

## STEP 3 — Test Image Intake

- **Test Image Selected:** `data/images/15970.jpg` (Turtle Check Men Navy Blue Shirt, verified 44k catalog item).
- **Deployment Status:** Blocked. Because the deployed frontend is the legacy research agent rather than the unified visual search UI, the test image cannot be submitted via a deployed UI dropzone.
- **Network Routing:** The active Vercel frontend dispatches WebSocket / REST requests exclusively to `https://research-agent-rpkp.onrender.com`.

---

## STEP 4 — Verify Vision Response

- Probing `POST https://research-agent-rpkp.onrender.com/search` and `POST https://research-agent-rpkp.onrender.com/api/v1/vision/process` returns **HTTP 404 Not Found**.
- Probing placeholder URL `https://visual-product-search-api.onrender.com` returns **HTTP 503 Service Unavailable**.
- **Assessment:** The deployed cloud backend does not expose the Vision pipeline.

---

## STEP 5 — Error / Resilience Check

- When an invalid or missing route is requested, the live Render service responds with standard JSON error payloads (`{"detail":"Not Found"}`).
- The local unified frontend (`frontend/src`) incorporates production-hardened error boundaries, file validation (0-byte detection, 25MB max size, JPG/PNG/WebP format enforcement), and retry mechanisms, but this resilience cannot be validated against a live cloud host until deployment is completed.

---

## STEP 6 — Same Pipeline Check (Anti-Cheat Verification)

- **Verification Directive:** Test must not accidentally use `localhost:8000`, local backend, local SQLite database, or local FAISS index.
- **Compliance:** Refused to fabricate a `PASS` by pointing requests to `http://127.0.0.1:8000` or `http://localhost:5173`.
- **Finding:** No local dependencies were used during remote evaluation; the missing cloud deployment is documented as a blocker.

---

## STEP 7 — Record Evidence

- **Deployed Frontend URL Tested:** `https://research-agent-five-delta.vercel.app/`
- **Deployed Backend URL Tested:** `https://research-agent-rpkp.onrender.com` (and placeholder `https://visual-product-search-api.onrender.com`)
- **Endpoints Tested:**
  - `GET https://research-agent-rpkp.onrender.com/health` → HTTP 200 (`{"status":"ok"}`)
  - `GET https://research-agent-rpkp.onrender.com/openapi.json` → HTTP 200 (Only `/runs...` endpoints mounted; no `/search` or `/api/v1/vision/process`)
  - `POST https://research-agent-rpkp.onrender.com/search` → HTTP 404 (`{"detail":"Not Found"}`)
  - `GET https://visual-product-search-api.onrender.com/health` → HTTP 503 (Service Unavailable)
- **Test Image Prepared:** `data/images/15970.jpg`
- **Product Results Loaded on Deployed UI:** None (UI missing)
- **Errors Encountered:** Remote endpoints return 404/503 for Vision operations.
- **Observed Remote Latency:** Render `/health` latency ~240ms; Vercel HTML response ~180ms.

---

## STEP 8 — Sign-off Decision

### Root Cause:
The unified application (combining Muneeb's Vision module, Faizan's RAG module, and Moeez's Agent module under `backend/app/gateway/main.py` and `frontend/`) has been fully integrated, hardened, and verified locally on branch `integration/final-base`, but has **not yet been deployed to a live cloud host** (Render/Railway/AWS for backend and Vercel for frontend).

### Smallest Next Fix:
1. **Deploy Unified Gateway Backend:**
   - Deploy `backend.app.gateway.main:app` as a Python/Docker container to Render or Railway.
   - Mount `artifacts/faiss/clip.index` and configure `DATABASE_PATH=data/catalog.db`, `CATALOG_IMAGES_DIR=data/images`, and `ALLOWED_ORIGINS`.
2. **Deploy Unified Frontend:**
   - Deploy `frontend/` to Vercel with `VITE_API_BASE_URL` pointing to the deployed backend.
3. **Execute Smoke Test:**
   - Upload `15970.jpg` via the deployed Vercel UI and verify ranked catalog cards return from the cloud backend.

---

## Final Report

WEEK 6 DAY 2 — MUNEEB VISION SMOKE TEST

Status: BLOCKED

Frontend:
- URL: Not deployed / Missing from project configuration (https://research-agent-five-delta.vercel.app/ serves legacy standalone agent, not unified Vision frontend)
- Result: Unable to test Vision intake on deployed frontend; unified Vite frontend has not been deployed to a live public host

Backend:
- URL: https://research-agent-rpkp.onrender.com (active standalone agent) / https://visual-product-search-api.onrender.com (503 Service Unavailable)
- Endpoint: POST /search, POST /api/v1/vision/process, GET /api/v1/vision/health
- Result: Unified gateway backend is not deployed to the cloud host; active Render instance only mounts standalone agent routes (/runs) and returns 404 for Vision routes

Image intake:
- Result: Blocked due to absence of live deployed unified frontend and backend

Vision processing:
- Result: Blocked on cloud deployment (all Vision processing and contract compliance verified locally, but remote deployment is absent)

Results display:
- Result: Blocked due to absence of deployed frontend

Errors encountered:
- Documented cloud backend (https://research-agent-rpkp.onrender.com) does not host the unified gateway or Vision routes
- Example production URL (https://visual-product-search-api.onrender.com) returns HTTP 503 Service Unavailable
- No live deployed URL exists for the unified frontend or unified gateway

Local dependency detected:
- No (strictly adhered to protocol; refused to substitute localhost, local backend, or local FAISS index)

Final sign-off:
- BLOCKED
