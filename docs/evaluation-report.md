# Visual Product Search — Comprehensive Evaluation & Architecture Report

**Project**: Visual Product Search System  
**Internship Milestone**: Week 3 Final Evaluation, Re-ranking & Database Finalization  
**Date**: August 2026  
**Selected Production Architecture**: OpenCLIP (`ViT-B-32`, `laion2b_s34b_b79k`) + FAISS `IndexIDMap2(IndexFlatIP)` + Hosted PostgreSQL (`pgvector`)

---

## 1. Dataset Discovery, Validation & Leakage-Free Splits

### 1.1 Dataset Discovery & Integrity Validation
The system operates on an expanded real-world catalog consisting of:
- **Raw Images Discovered**: 44,441 JPEG images in `data/images/`.
- **Raw Metadata Records**: 44,424 product styles in `data/styles.csv`.
- **Validation Audit**: 44,441 / 44,441 images were opened and validated using Pillow (0 corrupt, 0 truncated).
- **Matched Valid Manifest**: 44,419 verified image-metadata pairs recorded in [`data/manifests/validated_catalog_manifest.csv`](file:///d:/visual-product-search/data/manifests/validated_catalog_manifest.csv).

### 1.2 Leakage-Free Dataset Splitting
To prevent data contamination and evaluate generalization, the dataset was split deterministically (random seed `42`):
- **Searchable Catalog Split** ([`data/splits/catalog.csv`](file:///d:/visual-product-search/data/splits/catalog.csv)): **44,119 images** across 142 product categories.
- **Held-Out Validation Query Split** ([`data/splits/validation_queries.csv`](file:///d:/visual-product-search/data/splits/validation_queries.csv)): **100 clean queries** used strictly for parameter tuning.
- **Held-Out Final Test Query Split** ([`data/splits/test_queries.csv`](file:///d:/visual-product-search/data/splits/test_queries.csv)): **200 clean queries** held out until final testing.
- **Messy Query Variation Split** ([`evaluation/messy_query_manifest.csv`](file:///d:/visual-product-search/evaluation/messy_query_manifest.csv)): **200 realistic distorted queries** derived from the clean test set.

```text
Leakage Prevention Verification:
  [PASS] 0% leakage: Exactly 0 query images exist inside data/splits/catalog.csv.
  [PASS] Catalog items retain valid multi-image product pairs for query evaluation.
```

---

## 2. Ground-Truth Verification & Stable Database ID Mapping

### 2.1 Ground-Truth Inheritance
- Each query belongs to a verified multi-image product group.
- The ground truth is mapped to stable internal `catalog_item.id` primary keys recorded in [`data/manifests/catalog_id_map.csv`](file:///d:/visual-product-search/data/manifests/catalog_id_map.csv).
- All 300 queries (100 validation + 200 test) were reviewed and verified in [`evaluation/ground_truth.csv`](file:///d:/visual-product-search/evaluation/ground_truth.csv).

### 2.2 Stable Identity Hierarchy
```text
FAISS Search (Top-K)
      ↓ returns integer ID
catalog_item.id (Database Primary Key)
      ↓ SQL Batch Lookup (WHERE id = ANY(%s) / IN (...))
PostgreSQL Metadata + Image URL + 512-dim Embedding
```

---

## 3. Embedding Feature Representations & FAISS Index Architecture

Two model families were evaluated on the exact same 44,119 catalog rows:

| Specification | OpenCLIP ViT-B-32 (Selected) | ResNet-50 (Baseline) |
| :--- | :--- | :--- |
| **Model Identifier** | `open_clip:ViT-B-32:laion2b_s34b_b79k` | `torchvision.models.resnet50` (V2 Default) |
| **Feature Layer** | Multimodal Vision Transformer Head | Penultimate Average Pooled Layer |
| **Vector Dimension** | **512 float32** | 2048 float32 |
| **Normalization** | L2-normalized ($\|v\|_2 = 1.0$) | L2-normalized ($\|v\|_2 = 1.0$) |
| **FAISS Index Type** | `IndexIDMap2(IndexFlatIP(512))` | `IndexIDMap2(IndexFlatIP(2048))` |
| **FAISS Index Vectors** | **44,119** | **44,119** |
| **Index File Size** | **86.51 MB** | **345.02 MB** |

---

## 4. Re-ranking Architecture & Parameter Tuning

### 4.1 Re-ranking Pipeline
To capture fine-grained color distributions alongside high-level semantics, a secondary 64-dimensional HSV color histogram was extracted:
- **Feature Representation**: 32 Hue bins, 16 Saturation bins, 16 Value bins (L2-normalized).
- **Score Fusion**:
  $$S_{\text{combined}} = (1 - w_{\text{color}}) \times S_{\text{norm\_emb}} + w_{\text{color}} \times S_{\text{color}}$$
- **Tuning Set**: Tuned strictly on the 100 validation queries across 40 grid configurations.

### 4.2 Parameter Grid Search Highlights (Validation Queries)

| Initial Pool ($K$) | Color Weight ($w_{\text{color}}$) | Precision@1 | Precision@5 | Recall@5 | Hit@5 | MRR | Note |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **20** | **0.00 (Baseline)** | **0.2300** | **0.1060** | **0.2515** | **0.4000** | **0.3033** | **Optimal Configuration** |
| 20 | 0.20 | 0.2300 | 0.1060 | 0.2515 | 0.4000 | 0.3033 | Robust |
| 30 | 0.25 | 0.2300 | 0.1060 | 0.2515 | 0.4000 | 0.3033 | Robust |
| 50 | 0.40 | 0.2300 | 0.1040 | 0.2415 | 0.3900 | 0.3025 | Slight Category Drift |

*Frozen Configuration*: Persisted in [`evaluation/results/reranking_config.json`](file:///d:/visual-product-search/evaluation/results/reranking_config.json).

---

## 5. Complete 8-Condition Final Held-Out Evaluation Matrix

Evaluated across **200 held-out clean test queries** and **200 held-out messy test queries** (1,600 total evaluations):

| Experimental Condition | P@1 | P@5 | P@10 | R@1 | R@5 | R@10 | Hit@5 | MRR | Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CLIP baseline — clean test** | **0.2850** | **0.1180** | **0.0725** | **0.2162** | **0.3608** | **0.4286** | **0.4600** | **0.3626** | **141.7 ms** |
| **CLIP + reranking — clean test** | **0.2850** | **0.1180** | **0.0725** | **0.2162** | **0.3608** | **0.4286** | **0.4600** | **0.3635** | **138.7 ms** |
| **ResNet baseline — clean test** | 0.2350 | 0.0910 | 0.0580 | 0.1716 | 0.2691 | 0.3340 | 0.3800 | 0.3023 | 225.7 ms |
| **ResNet + reranking — clean test** | 0.2350 | 0.0910 | 0.0585 | 0.1716 | 0.2691 | 0.3347 | 0.3800 | 0.3029 | 229.8 ms |
| **CLIP baseline — messy test** | **0.1300** | **0.0650** | **0.0435** | **0.1013** | **0.2075** | **0.2687** | **0.2750** | **0.1895** | **138.8 ms** |
| **CLIP + reranking — messy test** | **0.1300** | **0.0650** | **0.0440** | **0.1013** | **0.2075** | **0.2707** | **0.2750** | **0.1904** | **143.2 ms** |
| **ResNet baseline — messy test** | 0.1300 | 0.0590 | 0.0335 | 0.0968 | 0.1760 | 0.2088 | 0.2450 | 0.1769 | 229.5 ms |
| **ResNet + reranking — messy test** | 0.1300 | 0.0590 | 0.0335 | 0.0968 | 0.1760 | 0.2088 | 0.2450 | 0.1773 | 222.8 ms |

---

## 6. Messy Query Robustness Analysis

Breakdown across 8 real-world visual transformations (25 queries each):

| Transformation Type | CLIP Precision@5 | CLIP Recall@5 | CLIP Hit@5 | ResNet Precision@5 | ResNet Recall@5 | ResNet Hit@5 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `small_rotation` | **0.1200** | **0.3986** | **0.4800** | 0.0880 | 0.2733 | 0.3600 |
| `darker_lighting` | **0.0960** | **0.2393** | **0.3600** | 0.0800 | 0.1633 | 0.3200 |
| `contrast_change` | 0.0640 | 0.2900 | 0.3200 | **0.0800** | **0.3680** | 0.3200 |
| `mild_perspective` | 0.0640 | 0.2137 | 0.2800 | **0.0880** | 0.2437 | **0.3600** |
| `brighter_lighting` | **0.0640** | **0.2133** | **0.2800** | 0.0400 | 0.1133 | 0.2000 |
| `crop` | **0.0560** | **0.1647** | **0.2800** | 0.0560 | 0.1633 | 0.2400 |
| `background_padding` | 0.0320 | **0.1000** | **0.1200** | **0.0400** | 0.0833 | **0.1600** |
| `blur` | **0.0240** | **0.0400** | **0.0800** | 0.0000 | 0.0000 | 0.0000 |

*Key Robustness Insight*: ResNet-50 suffers complete failure on defocus blur (0.0% hit rate), whereas OpenCLIP maintains partial semantic retrieval. Both models demonstrate resilience to minor rotations ($\pm 8^\circ$) and darker illumination.

---

## 7. Database Architecture & pgvector Integration

### 7.1 Separation of Concerns: FAISS vs PostgreSQL
- **FAISS (`artifacts/faiss/clip.index`)**: Serves as the in-memory, ultra-fast vector index executing approximate inner-product searches in **<20 ms**.
- **Hosted PostgreSQL (`pgvector`)**: Acts as the persistent system of record holding relational product metadata, category taxonomy, audit logs, and durable 512-dim vector backups.

### 7.2 Schema Definition (`catalog_items`)
```sql
CREATE TABLE IF NOT EXISTS catalog_items (
    id SERIAL PRIMARY KEY,
    image_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    filename VARCHAR(255) NOT NULL,
    relative_path VARCHAR(500) NOT NULL,
    image_url VARCHAR(500) NOT NULL,
    category VARCHAR(100),
    sub_category VARCHAR(100),
    article_type VARCHAR(100),
    base_colour VARCHAR(50),
    season VARCHAR(50),
    year INTEGER,
    usage VARCHAR(50),
    product_display_name TEXT,
    width INTEGER,
    height INTEGER,
    file_size_bytes BIGINT,
    embedding vector(512),
    embedding_dimension INTEGER,
    embedding_model VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_catalog_items_product_id ON catalog_items (product_id);
CREATE INDEX IF NOT EXISTS idx_catalog_items_category ON catalog_items (category);
```

### 7.3 Single Production Embedding Import
In accordance with the project policy, **only OpenCLIP 512-dimensional vectors** are stored in `catalog_items.embedding` (44,119 / 44,119 rows populated). ResNet embeddings remain strictly in offline audit files (`artifacts/embeddings/resnet_embeddings.npy`).

---

## 8. Summary of Final Technical Decisions

1. **Production Model**: OpenCLIP `ViT-B-32` (`laion2b_s34b_b79k`) selected for superior recall (**+34.1% over ResNet**), lower query latency (**141.7 ms vs 225.7 ms**), and smaller index footprint (**86.5 MB vs 345.0 MB**).
2. **Deterministic Stability**: All API responses map integer FAISS IDs directly to PostgreSQL primary keys in **O(1) batch lookup time** while preserving ranking order.
3. **Robustness Safeguards**: Input images undergo PIL integrity decoding, bounding checks, and fallback serving.
