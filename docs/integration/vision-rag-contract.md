# Vision → RAG Integration Contract (Week 4)

**Document Version:** 2.0.0 (Frozen Specification)  
**Status:** FROZEN FOR IMPLEMENTATION  
**Module:** Computer Vision / Visual Product Search  
**Lead:** Muneeb Ur Rehman  
**Target Consumers:** Faizan (RAG Module) / Moeez (Multi-Agent Orchestrator)  
**Pipeline Sequence:** `Client / Orchestrator → Vision → Shared DB (extracted_data) → RAG → Agent`

---

## 1. Overview & Preservation of Existing Search Architecture

This document defines the frozen, canonical integration contract for the Computer Vision module in Week 4.

> [!IMPORTANT]
> **Preservation Guarantee for Weeks 1–3 System**:
> All existing visual search infrastructure remains fully functional and unmodified:
> - **Existing Endpoints:** `POST /search` and `POST /api/v1/search` remain active for the frontend web application and legacy clients.
> - **Internal Pipeline:** Image decoding $\rightarrow$ OpenCLIP ViT-B-32 / ResNet-50 feature extraction $\rightarrow$ FAISS `IndexIDMap2` vector search $\rightarrow$ Order-preserving database catalog metadata lookup.
> - **FAISS ID Mapping:** FAISS vector IDs map directly 1:1 to integer database primary keys (`catalog_items.id`). This mapping is strictly preserved.
> - **Vector Index Storage:** Local FAISS binary indexes (`artifacts/faiss/clip.index` and `artifacts/faiss/resnet.index`) remain the high-performance search backend for the 44,119 product catalog. FAISS is not replaced, and catalog vectors are not moved into PostgreSQL.

---

## 2. Integration Endpoint Specification

### `POST /api/v1/vision/process`

* **Protocol:** HTTP / REST
* **Content-Type:** `multipart/form-data`
* **Authentication:** Consistent with shared pipeline configuration (optional Bearer token / open internal service).

### Request Fields

| Field Name | Type | Presence | Description & Constraints |
| :--- | :--- | :--- | :--- |
| `image` | `UploadFile` (binary) | **Required** | Query image file. Supported formats follow existing working validation (`JPEG`, `PNG`, `WebP`). Verified via PIL decoding. |
| `pipeline_run_id` | `str` (UUID) | **Required** | Unique execution trace identifier assigned and supplied by the orchestrator. **Vision must NOT generate a replacement ID if missing.** If omitted or invalid, return HTTP `400 / 422`. |
| `top_k` | `int` | Optional | Number of candidate products to return. Allowed range: `1` to `50`. Default: `10`. |
| `model` | `str` | Optional | Visual embedding model. Canonical supported values: `"clip"` (default) or `"resnet"`. |

> [!NOTE]
> Canonical model values for the integration contract are strictly `"clip"` and `"resnet"`. (Legacy aliases such as `"resnet50"` supported on `/search` do not form part of the official integration contract).

---

## 3. Required Successful API Response Schema

The successful API response returned by `POST /api/v1/vision/process` must contain **exactly** these top-level contract fields:

```json
{
  "pipeline_run_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "status": "completed",
  "primary_match": {
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
  },
  "matches": [
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
    },
    {
      "rank": 2,
      "catalog_item_id": 14210,
      "product_id": 18245,
      "external_id": "18245",
      "filename": "18245.jpg",
      "product_display_name": "Locomotive Men Check Green Casual Shirt",
      "category": "Apparel",
      "sub_category": "Topwear",
      "article_type": "Shirts",
      "base_colour": "Green",
      "gender": "Men",
      "season": "Fall",
      "usage": "Casual",
      "image_url": "/catalog-images/18245.jpg",
      "similarity_score": 0.8842
    }
  ],
  "confidence": 0.9179,
  "extracted_data_id": "4a2c9f50-618d-4f18-bb54-7128d39e2b11"
}
```

### Top-Level Fields Specification

| Field | Type | Description |
| :--- | :--- | :--- |
| `pipeline_run_id` | `str` (UUID) | Matches the input `pipeline_run_id` received in the request. |
| `status` | `str` | Fixed string: `"completed"`. |
| `primary_match` | `Dict[str, Any]` | The Rank-1 candidate product dictionary. |
| `matches` | `List[Dict[str, Any]]` | Full list of Top-$K$ ranked candidate product dictionaries ($1 \dots K$). |
| `confidence` | `float` | Scalar similarity metric of the Rank-1 result (`primary_match.similarity_score`). |
| `extracted_data_id` | `str` (UUID) | Primary key ID of the record inserted into the shared `extracted_data` table. |

> [!CAUTION]
> **No Unapproved Top-Level Fields**:
> Top-level fields from earlier draft proposals such as `producer`, `match_status`, and `error` are **omitted** from the successful contract.

---

## 4. Match Object Schema & Product Identifiers

Individual product objects in `primary_match` and `matches` strictly reuse fields from the existing Weeks 1–3 catalog database schema:

| Field Name | Type | Nullable | Description |
| :--- | :--- | :---: | :--- |
| `rank` | `int` | No | 1-based similarity rank position ($1, 2, \dots, K$). |
| `catalog_item_id` | `int` | No | Internal catalog database primary key ID (`catalog_items.id`). Matches FAISS index ID 1:1. |
| `product_id` | `int` | No | Source product identifier from dataset. |
| `external_id` | `str` | Yes | Unique external product string ID. |
| `filename` | `str` | No | Catalog image filename (e.g., `"37779.jpg"`). |
| `product_display_name` | `str` | Yes | Human-readable product title / name. |
| `category` | `str` | Yes | Master category (e.g., `"Apparel"`, `"Footwear"`). |
| `sub_category` | `str` | Yes | Sub-category (e.g., `"Topwear"`, `"Shoes"`). |
| `article_type` | `str` | Yes | Specific product type (e.g., `"Shirts"`, `"Tshirts"`). |
| `base_colour` | `str` | Yes | Dominant product color (e.g., `"Green"`, `"Navy Blue"`). |
| `gender` | `str` | Yes | Target gender / demographic (e.g., `"Men"`, `"Women"`). |
| `season` | `str` | Yes | Seasonal classification (e.g., `"Summer"`, `"Fall"`). |
| `usage` | `str` | Yes | Usage context (e.g., `"Casual"`, `"Formal"`). |
| `image_url` | `str` | No | Endpoint URL to access the product image (e.g., `"/catalog-images/37779.jpg"`). |
| `similarity_score` | `float` | No | Continuous similarity metric computed by FAISS Inner Product on $L_2$-normalized vectors. |

---

## 5. Confidence & Similarity Semantics

1. **Mathematical Representation:**
   Query vectors and catalog vectors are $L_2$-normalized ($\|v\|_2 = 1.0$). Under FAISS `IndexFlatIP` (Inner Product), the computed similarity is exact **Cosine Similarity**:
   $$\text{similarity\_score} = \langle \hat{u}, \hat{v} \rangle = \cos(\theta)$$
2. **Confidence Value:**
   `confidence` in the response is set to the Rank-1 candidate's `similarity_score` (`primary_match["similarity_score"]`).
3. **Important Semantic Rules:**
   - `confidence` is a continuous **ranking/similarity metric**, NOT a calibrated posterior probability.
   - Do **NOT** convert `confidence` into a percentage (e.g., do not describe `0.9179` as `"91.79% confidence"`).
   - Theoretical range is $[-1.0, 1.0]$. In empirical catalog evaluations, natural image matches typically range between `0.30` and `0.95` (and `1.0000` for exact identical images).

---

## 6. Shared PostgreSQL Database Responsibilities

The shared Week 4 PostgreSQL database coordinates pipeline state across modules (`Vision → RAG → Agent`).

### Ownership Boundaries

| Module | Owns Table Writes To | Read Access |
| :--- | :--- | :--- |
| **Vision (Muneeb)** | `assets`, `extracted_data`, `module_events` | Reads catalog items; writes vision artifacts. |
| **RAG (Faizan)** | `rag_documents`, `rag_chunks`, `rag_queries` | Reads `extracted_data` (Vision handoff); writes knowledge chunks. |
| **Agent / Orchestrator (Moeez)** | `pipeline_runs`, `chat_history`, `agent_runs`, `agent_actions` | Manages overall run lifecycle and tool invocation. |

### Proposed Table Schemas for Vision Records

> [!NOTE]
> All shared table schemas below represent proposed Vision fields pending final multi-module schema review with Faizan and Moeez.

#### 1. `assets` Table (Proposed)
Records uploaded input images associated with a pipeline run.

```sql
CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id UUID NOT NULL,
    asset_type TEXT NOT NULL DEFAULT 'query_image',
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### 2. `extracted_data` Table (Proposed — Vision → RAG Handoff)
Stores structured visual search output. The `id` of this record is returned as `extracted_data_id` in the API response.

```sql
CREATE TABLE IF NOT EXISTS extracted_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id UUID NOT NULL,
    asset_id UUID REFERENCES assets(id),
    module TEXT NOT NULL DEFAULT 'vision',
    data_type TEXT NOT NULL DEFAULT 'visual_product_search_matches',
    content JSONB NOT NULL,
    model TEXT NOT NULL,
    confidence FLOAT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

* `content JSONB` holds the complete structured payload: `{"primary_match": {...}, "matches": [...]}`.
* `extracted_data_id` $\equiv$ `extracted_data.id`.

#### 3. `module_events` Table (Proposed — Lifecycle Auditing)
Audit log tracking execution stages across modules.

```sql
CREATE TABLE IF NOT EXISTS module_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id UUID NOT NULL,
    module TEXT NOT NULL,
    event TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Standardized Event Payloads for Vision:**

* **Started:**
  ```json
  {
    "pipeline_run_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "module": "vision",
    "event": "started",
    "message": "Visual search started."
  }
  ```
* **Completed:**
  ```json
  {
    "pipeline_run_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "module": "vision",
    "event": "completed",
    "message": "Visual search completed."
  }
  ```
* **Failed:**
  ```json
  {
    "pipeline_run_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "module": "vision",
    "event": "failed",
    "message": "Visual search failed: <reason>"
  }
  ```

---

## 7. Error Handling & HTTP Status Semantics

The integration endpoint enforces standard HTTP error status codes. Validation failures and server errors do **not** return HTTP 200.

| Error Scenario | HTTP Status | Error Detail Format | Action on `module_events` |
| :--- | :---: | :--- | :--- |
| **Missing `pipeline_run_id`** | `422 / 400` | `{"detail": "Missing required field: pipeline_run_id."}` | Cannot log event (no trace ID). |
| **Invalid UUID format** | `422 / 400` | `{"detail": "pipeline_run_id must be a valid UUID."}` | Cannot log event. |
| **Missing image file** | `400` | `{"detail": "Image file is required."}` | If `pipeline_run_id` present, log `failed` event. |
| **Corrupt / unreadable image** | `400` | `{"detail": "Uploaded file is not a valid or supported image."}` | Log `failed` event. |
| **Invalid `top_k` (not 1–50)** | `400` | `{"detail": "top_k must be an integer between 1 and 50."}` | Log `failed` event. |
| **Unsupported `model`** | `400` | `{"detail": "Unsupported model. Allowed values: 'clip', 'resnet'."}` | Log `failed` event. |
| **Internal search / FAISS error** | `500` | `{"detail": "Visual search processing error: <error details>"}` | Log `failed` event. |
| **Shared DB persistence error** | `500` | `{"detail": "Failed to persist extracted data to shared database."}` | Do not return `completed` if persistence fails. |

---

## 8. Database Separation & Environment Configuration

The Vision catalog storage and the Week 4 shared pipeline database remain strictly separated:

1. **Vision Catalog Database:**
   - Local SQLite (`data/catalog.db`) or existing PostgreSQL catalog table (`catalog_items`).
   - Contains 44,119 product metadata rows, images, and catalog attributes.
   - Vector queries execute directly against FAISS index files in RAM (`artifacts/faiss/*`).
2. **Shared Week 4 PostgreSQL Database:**
   - Multi-module database storing pipeline runs, assets, extracted data, RAG chunks, and module audit logs.
   - Vision connects solely to insert into `assets`, `extracted_data`, and `module_events`.

### Proposed Environment Variables

```bash
# Vision Catalog Database (Existing)
CATALOG_DATABASE_PATH=data/catalog.db
# or CATALOG_DATABASE_URL=postgresql://...

# Shared Week 4 Integration Database (Proposed)
SHARED_DATABASE_URL=postgresql://postgres:password@shared-host:5432/shared_ai_assistant

# Storage paths
CATALOG_IMAGES_DIR=data/images
FAISS_INDEX_DIR=artifacts/faiss
```

---

## 9. Vision → RAG Sequence Diagram & Execution Flow

```mermaid
sequenceDiagram
    autonumber
    actor Client as Orchestrator / Client
    participant API as POST /api/v1/vision/process
    participant Svc as VisionPipelineAdapter
    participant DBShared as Shared PostgreSQL
    participant Search as CLIP / ResNet + FAISS
    participant DBCatalog as Catalog DB (SQLite/PG)
    actor RAG as Faizan RAG Module

    Client->>API: multipart/form-data (image, pipeline_run_id, top_k, model)
    API->>Svc: Validate image & pipeline_run_id
    Svc->>DBShared: INSERT INTO module_events ('started')
    Svc->>DBShared: INSERT INTO assets (image metadata) -> asset_id
    Svc->>Search: Search FAISS Index (OpenCLIP / ResNet)
    Search-->>Svc: Top-K FAISS IDs (catalog_items.id) + cosine scores
    Svc->>DBCatalog: fetch_catalog_items_by_ids(catalog_ids)
    DBCatalog-->>Svc: Ordered product metadata
    Svc->>Svc: Construct primary_match, matches, confidence
    Svc->>DBShared: INSERT INTO extracted_data (content JSONB, confidence) -> extracted_data_id
    Svc->>DBShared: INSERT INTO module_events ('completed')
    Svc-->>API: Response JSON
    API-->>Client: 200 OK (pipeline_run_id, status, primary_match, matches, confidence, extracted_data_id)
    Client->>RAG: Trigger RAG with extracted_data_id / primary_match
    RAG->>DBShared: SELECT content FROM extracted_data WHERE id = extracted_data_id
```

---

## 10. Alignment & Canonical Document Consolidation

* **Canonical Document:** This document ([docs/integration/vision-rag-contract.md](file:///d:/visual-product-search/docs/integration/vision-rag-contract.md)) is the **sole authoritative reference** for the Week 4 Vision $\rightarrow$ RAG integration contract.
* **Legacy Document Resolution:** The draft document [docs/vision-integration-contract.md](file:///d:/visual-product-search/docs/vision-integration-contract.md) has been updated to explicitly redirect to this canonical specification, eliminating conflicting schemas (`producer`, `match_status`, etc.).

---

*Contract frozen on: Week 4 Day 2.*
