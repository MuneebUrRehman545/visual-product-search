# Visual Product Search Engine

A high-performance visual product search system built with Python, PyTorch, OpenCLIP, SQLite, and FAISS. The system converts product catalog images into normalized vector embeddings and enables real-time visual similarity search across catalog items.

---

## Architecture Overview

```text
                          ┌───────────────────────────┐
                          │   Query Image Input       │
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │  Embedding Service        │
                          │  (OpenCLIP ViT-B/32)      │
                          └─────────────┬─────────────┘
                                        │ 512-dim normalized float32
                                        ▼
                          ┌───────────────────────────┐
                          │  FAISS Index Search       │
                          │  (IndexIDMap2(FlatIP))    │
                          └─────────────┬─────────────┘
                                        │ SQLite Product IDs & Scores
                                        ▼
                          ┌───────────────────────────┐
                          │  SQLite Database Lookup   │
                          │  (data/catalog.db)        │
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │  Ranked Results Output    │
                          └───────────────────────────┘
```

---

## Core System Components

### 1. Catalog & Manifest Dataset
- **Catalog Manifest**: [`data/catalog/manifest_2000.csv`](file:///d:/visual-product-search/data/catalog/manifest_2000.csv) contains 2,000 validated product records (`product_id`, `image_path`, `filename`, `category`).
- **Metadata Database**: SQLite database at [`data/catalog.db`](file:///d:/visual-product-search/data/catalog.db) with table schema `products(id, external_id, image_path, filename, category, embedding_dimension, created_at)`.

### 2. Primary Embedding Model & Vector Index
- **Model**: OpenCLIP `ViT-B-32` (`laion2b_s34b_b79k`).
- **Vector Dimension**: 512 float32 values (L2-normalized).
- **FAISS Index Structure**: `faiss.IndexFlatIP(512)` wrapped in `faiss.IndexIDMap2` stored at [`data/embeddings/clip_vit_b32/catalog.index`](file:///d:/visual-product-search/data/embeddings/clip_vit_b32/catalog.index).
- **ID Mapping**: SQLite primary key product IDs explicitly mapped using `product_ids.npy` via `index.add_with_ids()`.

### 3. Ingestion Pipeline
- Batch-processed image feature extraction (`batch_size=64`).
- Concurrent metadata upserts to SQLite database.
- Automatic FAISS index building and disk reload verification.

---

## Project Structure

```text
D:\visual-product-search
├── app/
│   ├── db/
│   │   └── database.py                # SQLite database interface & context manager
│   └── services/
│       ├── embedding_service.py        # OpenCLIP ViT-B/32 embedding service
│       ├── clip_search_service.py     # CLIP FAISS visual search service
│       ├── resnet_embedding_service.py # ResNet-50 embedding service
│       └── resnet_search_service.py   # ResNet-50 FAISS search service
├── data/
│   ├── catalog/
│   │   └── manifest_2000.csv          # 2,000-product manifest
│   ├── catalog.db                     # SQLite catalog database
│   ├── embeddings/
│   │   ├── clip_vit_b32/              # CLIP 512-dim index & embeddings
│   │   └── resnet50/                  # ResNet-50 2048-dim index & embeddings
│   └── evaluation/
│       ├── queries/                   # Evaluation query images
│       ├── ground_truth.csv           # Ground truth relevance mapping
│       ├── per_query_results.csv      # Per-query evaluation metrics
│       └── comparison_results.json    # Summary evaluation report
├── docs/
│   └── embedding-comparison.md        # Model evaluation benchmark document
├── scripts/
│   ├── ingest_catalog.py              # CLIP 2000-image catalog ingestion
│   ├── ingest_resnet_catalog.py       # ResNet-50 catalog ingestion
│   ├── build_faiss_index.py           # CLIP FAISS index builder
│   ├── build_resnet_faiss_index.py    # ResNet-50 FAISS index builder
│   ├── evaluate_embeddings.py         # Precision/Recall/Latency evaluation script
│   ├── verify_ingestion.py            # System integrity verification suite
│   ├── compare_single_query.py        # Single image side-by-side comparison
│   └── smoke_test_search.py           # Week 2 readiness smoke test
├── requirements.txt
└── README.md
```

---

## Measured Performance Metrics

Based on the empirical benchmark run across 25 evaluation queries (`data/evaluation/comparison_results.json`):

| Metric | CLIP (ViT-B/32) | ResNet-50 |
| :--- | :--- | :--- |
| **Precision@1** | **0.9200** | 0.8400 |
| **Precision@5** | **0.2000** | 0.1840 |
| **Recall@1** | **0.9000** | 0.8200 |
| **Recall@5** | **0.9800** | 0.9000 |
| **Average Latency** | **128.43 ms** | 165.46 ms |
| **Median Latency** | **119.41 ms** | 148.80 ms |

---

## Local Run Commands

### 1. Environment Setup
```powershell
# Activate Python virtual environment
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Catalog Ingestion & Index Building (2,000 Images)
```powershell
# Run full CLIP 2,000-image batch ingestion pipeline
python scripts/ingest_catalog.py
```

### 3. Verify System Integrity
```powershell
# Verify DB count (2000), FAISS count (2000), embedding shapes, and path validity
python scripts/verify_ingestion.py
```

### 4. Run Smoke Test & Single Query Search
```powershell
# Run random 5-query readiness smoke test
python scripts/smoke_test_search.py

# Compare CLIP vs ResNet-50 search side-by-side on a query image
python scripts/compare_single_query.py --top-k 5
```

### 5. Run Model Benchmark Evaluation
```powershell
# Execute precision, recall, and latency evaluation benchmark
python scripts/evaluate_embeddings.py
```
