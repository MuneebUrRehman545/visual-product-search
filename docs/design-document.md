# Visual Product Search — Design Document

## 1. Project Overview

This project implements a visual product search system that retrieves catalog items similar to a user-provided image. Instead of relying only on product names, tags, or text metadata, the system converts images into numerical feature vectors called embeddings and searches for nearby vectors using FAISS.

The current implementation compares two image embedding approaches:

- CLIP ViT-B/32
- ResNet-50 feature embeddings

Both approaches use the same catalog images, SQLite product records, query images, ground-truth labels, similarity method, and evaluation metrics. CLIP is currently selected as the main search approach because it achieved stronger measured retrieval accuracy and lower query latency on the labeled evaluation set.

## 2. Dataset

A 100-image product catalog was selected from a larger public dataset containing approximately 44,000 images.

Catalog location:

```text
data/catalog/images/
```

The 100-image subset is used for the Week 1 ingestion pipeline and initial system evaluation. Images are processed recursively, and the supported formats are:

- `.jpg`
- `.jpeg`
- `.png`
- `.webp`

A separate evaluation set contains 25 labeled query images with realistic variations such as:

- Changed background
- Changed lighting
- Different viewing angle
- Different crop
- Partial occlusion
- Phone-camera capture

Evaluation files:

```text
data/evaluation/queries/
data/evaluation/ground_truth.csv
```

## 3. Embedding Approaches

### 3.1 CLIP ViT-B/32

The primary approach uses the CLIP ViT-B/32 image encoder with pretrained weights.

Processing steps:

1. Open the image using Pillow.
2. Convert it to RGB.
3. Apply the model-specific preprocessing transform.
4. Generate a 512-dimensional image embedding.
5. Apply L2 normalization.
6. Store the embedding as a NumPy `float32` array.
7. Add the embedding to a FAISS inner-product index.

Because embeddings are normalized, inner-product similarity is equivalent to cosine similarity.

CLIP output files:

```text
data/embeddings/clip_vit_b32/catalog_embeddings.npy
data/embeddings/clip_vit_b32/product_ids.npy
data/embeddings/clip_vit_b32/catalog.index
data/embeddings/clip_vit_b32/ingestion_report.json
```

### 3.2 ResNet-50

The second approach uses a pretrained ResNet-50 model from `torchvision`. The final classification layer is removed, and the 2048-dimensional global feature vector is used as the image embedding.

Processing steps:

1. Open the image using Pillow.
2. Convert it to RGB.
3. Apply the preprocessing transform associated with the pretrained weights.
4. Pass the image through the ResNet-50 backbone.
5. Extract the 2048-dimensional feature vector before classification.
6. Apply L2 normalization.
7. Store the embedding as a NumPy `float32` array.
8. Add the embedding to a separate FAISS inner-product index.

ResNet-50 output files:

```text
data/embeddings/resnet50/catalog_embeddings.npy
data/embeddings/resnet50/product_ids.npy
data/embeddings/resnet50/catalog.index
data/embeddings/resnet50/ingestion_report.json
```

## 4. System Architecture

### 4.1 Catalog Ingestion Architecture

```text
+----------------------------+
| Product Catalog Images     |
| data/catalog/images/       |
+-------------+--------------+
              |
              v
+----------------------------+
| Image Validation and       |
| Preprocessing              |
| Pillow + model transforms  |
+-------------+--------------+
              |
              +------------------------------+
              |                              |
              v                              v
+----------------------------+  +----------------------------+
| CLIP ViT-B/32 Encoder      |  | ResNet-50 Encoder          |
| 512-dimensional embedding  |  | 2048-dimensional embedding |
+-------------+--------------+  +-------------+--------------+
              |                              |
              v                              v
+----------------------------+  +----------------------------+
| L2-normalized NumPy array  |  | L2-normalized NumPy array  |
| float32                    |  | float32                    |
+-------------+--------------+  +-------------+--------------+
              |                              |
              v                              v
+----------------------------+  +----------------------------+
| CLIP FAISS Index           |  | ResNet-50 FAISS Index      |
| IndexIDMap2 + IndexFlatIP  |  | IndexIDMap2 + IndexFlatIP  |
+-------------+--------------+  +-------------+--------------+
              |                              |
              +---------------+--------------+
                              |
                              v
                 +----------------------------+
                 | SQLite Product Database    |
                 | Product metadata and IDs   |
                 +----------------------------+
```

### 4.2 Query Search Architecture

```text
+----------------------------+
| User Query Image           |
+-------------+--------------+
              |
              v
+----------------------------+
| Image Validation and       |
| Preprocessing              |
+-------------+--------------+
              |
              v
+----------------------------+
| Selected Embedding Model   |
| CLIP or ResNet-50          |
+-------------+--------------+
              |
              v
+----------------------------+
| Normalized Query Embedding |
+-------------+--------------+
              |
              v
+----------------------------+
| Corresponding FAISS Index  |
| Top-K inner-product search |
+-------------+--------------+
              |
              v
+----------------------------+
| FAISS Product IDs          |
+-------------+--------------+
              |
              v
+----------------------------+
| SQLite Metadata Lookup     |
+-------------+--------------+
              |
              v
+----------------------------+
| Ranked Similar Products    |
| IDs, paths, categories,    |
| scores, and ranking        |
+----------------------------+
```

### 4.3 Component Responsibilities

| Component | Responsibility |
|---|---|
| Embedding services | Load models, preprocess images, and generate normalized embeddings |
| Ingestion scripts | Process the catalog, insert product records, and save embeddings |
| SQLite database | Store product IDs and metadata |
| NumPy files | Store catalog embedding matrices and matching product ID arrays |
| FAISS indexes | Perform nearest-neighbor similarity search |
| Search services | Generate query embeddings, search FAISS, and fetch metadata |
| Evaluation script | Compare CLIP and ResNet-50 using the same labeled queries |
| FastAPI backend | Expose health and visual-search endpoints |
| Frontend | Allow image upload or capture and display ranked results |

## 5. Database Design

SQLite is used for local development. The database file is:

```text
data/catalog.db
```

The database stores product metadata. Embeddings are not stored as SQLite blobs. Instead, embeddings are stored in NumPy arrays, while a separate product ID array preserves the mapping between every FAISS vector and its SQLite product record.

### 5.1 Products Table Schema

```sql
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    image_path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    category TEXT,
    embedding_dimension INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
```

### 5.2 Schema Description

| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `id` | INTEGER | Primary key, auto-increment | Internal product ID used by SQLite and FAISS |
| `external_id` | TEXT | Not null, unique | Stable identifier derived from metadata or filename |
| `image_path` | TEXT | Not null, unique | Image path relative to the project root |
| `filename` | TEXT | Not null | Original catalog image filename |
| `category` | TEXT | Nullable | Product category when available |
| `embedding_dimension` | INTEGER | Not null | Dimension of the embedding associated with the ingestion record |
| `created_at` | TEXT | Not null | Record creation timestamp |

## 6. FAISS-to-Database ID Mapping

The system does not assume that a vector row number equals a database product ID.

For each embedding approach:

```text
catalog_embeddings.npy row i
            |
            v
product_ids.npy row i
            |
            v
SQLite products.id
            |
            v
Product metadata and image path
```

FAISS uses `IndexIDMap2`, allowing catalog vectors to be added with actual SQLite product IDs.

This guarantees that:

- Search results can be mapped reliably to product records.
- Database IDs can remain stable even if embeddings are regenerated.
- CLIP and ResNet-50 indexes can use the same product records.
- Vector order does not need to match database insertion order.

## 7. Repository Structure

```text
visual-product-search/
├── app/
│   ├── db/
│   │   └── database.py
│   ├── services/
│   │   ├── embedding_service.py
│   │   ├── resnet_embedding_service.py
│   │   ├── clip_search_service.py
│   │   └── resnet_search_service.py
│   └── main.py
├── data/
│   ├── catalog/
│   │   └── images/
│   ├── embeddings/
│   │   ├── clip_vit_b32/
│   │   └── resnet50/
│   ├── evaluation/
│   │   ├── queries/
│   │   ├── ground_truth.csv
│   │   ├── per_query_results.csv
│   │   └── comparison_results.json
│   └── catalog.db
├── docs/
│   ├── design-document.md
│   └── embedding-comparison.md
├── scripts/
│   ├── ingest_catalog.py
│   ├── ingest_resnet_catalog.py
│   ├── build_faiss_index.py
│   ├── build_resnet_faiss_index.py
│   ├── verify_ingestion.py
│   ├── verify_resnet_ingestion.py
│   ├── compare_single_query.py
│   └── evaluate_embeddings.py
├── requirements.txt
├── .env.example
└── .gitignore
```

The exact repository tree should be updated if filenames in the implementation differ.

## 8. Evaluation Summary

Both models were evaluated using the same 25 labeled query images.

| Metric | CLIP ViT-B/32 | ResNet-50 |
|---|---:|---:|
| Precision@1 | 0.9200 | 0.8400 |
| Precision@5 | 0.2000 | 0.1840 |
| Precision@10 | 0.1000 | 0.0960 |
| Recall@1 | 0.9000 | 0.8200 |
| Recall@5 | 0.9800 | 0.9000 |
| Recall@10 | 0.9800 | 0.9400 |
| Average latency | 116.10 ms | 148.98 ms |
| Median latency | 110.72 ms | 142.99 ms |

CLIP achieved higher Precision@1, Recall@1, Recall@5, and lower average and median query latency. Based on the measured evaluation, CLIP ViT-B/32 is selected as the default production search approach. ResNet-50 remains available as a comparison baseline.

## 9. Technology Choices

| Area | Technology | Reason |
|---|---|---|
| Image processing | Pillow | Lightweight and compatible with PyTorch transforms |
| Main embedding | CLIP ViT-B/32 | Strong semantic and visual retrieval performance |
| Baseline embedding | ResNet-50 | Established CNN feature baseline |
| Model runtime | PyTorch | Supports both embedding approaches |
| Similarity search | FAISS CPU | Free, local, fast, and scalable beyond brute-force loops |
| Local database | SQLite | Simple local development and reliable metadata storage |
| Backend | FastAPI | Natural fit for Python model inference and file uploads |
| Frontend | React or Next.js | Mobile-responsive deployable web interface |
| Deployment database | PostgreSQL | Planned hosted database for the deployed version |

## 10. Limitations and Next Steps

Current limitations:

- The initial catalog contains only approximately 100 images.
- The evaluation set contains 25 manually labeled queries.
- Some variation groups contain only a small number of examples.
- SQLite is suitable for local development but not the final hosted deployment.
- Re-ranking has not yet been included in the architecture.
- Deployment and frontend integration remain separate milestones.

Next development steps:

1. Expose the selected search service through a FastAPI endpoint.
2. Build the image upload and ranked-results frontend.
3. Expand the catalog to 500–2,000 images.
4. Implement and evaluate a re-ranking signal.
5. Deploy the frontend, backend, and hosted database.
