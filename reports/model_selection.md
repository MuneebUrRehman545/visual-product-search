# Production Retrieval Pipeline Selection Report

**Project**: Visual Product Search — Week 3 Evaluation & Deployment  
**Date**: August 2026  
**Status**: **FROZEN FOR PRODUCTION DEPLOYMENT**  
**Selected Model**: **OpenCLIP (ViT-B-32, `laion2b_s34b_b79k`)**  
**Configuration File**: [`artifacts/production_model.json`](file:///d:/visual-product-search/artifacts/production_model.json)

---

## 1. Executive Summary & Selection Decision

Based on rigorous held-out evaluation across **200 clean test queries** and **200 realistic messy queries** against the full **44,119 searchable catalog images**, **OpenCLIP ViT-B-32** is selected as the primary production retrieval engine.

### Key Justification Highlights
1. **Dominant Semantic Retrieval Accuracy**: OpenCLIP outperforms ResNet-50 by **+34.1% relative Recall@5** (0.3608 vs 0.2691) and **+29.7% relative Precision@5** (0.1180 vs 0.0910) on the held-out clean test set.
2. **Robustness to Real-World Visual Distortions**: Under severe messy transforms (blur, lighting, rotation, framing shifts), CLIP maintains a **+17.9% higher Recall@5** over ResNet-50. ResNet completely collapses to 0.0% recall on defocused blurred images, whereas CLIP retains usable retrievals.
3. **37% Lower End-to-End Query Latency**: CLIP processes queries in **141.7 ms** compared to ResNet-50's **225.7 ms** (84 ms faster), primarily driven by FAISS inner product search over 512-dimensional vectors (18.9 ms) vs 2048-dimensional vectors (54.2 ms).
4. **4x Lower Storage & pgvector Index Overhead**: CLIP requires only **512 float32 dimensions (2.0 KB per item / 88 MB full catalog)** compared to ResNet's **2048 dimensions (8.0 KB per item / 353 MB full catalog)**, minimizing hosted PostgreSQL memory footprint and index build overhead.

---

## 2. Evaluation Candidates

Four candidate pipelines were systematically benchmarked on identical catalog items and ground-truth sets:

| Candidate | Embedding Model | Vector Dim | Similarity Metric | Second-Stage Re-ranking |
| :--- | :--- | :--- | :--- | :--- |
| **1. CLIP Baseline** | OpenCLIP ViT-B-32 (`laion2b_s34b_b79k`) | 512 | Cosine / Inner Product | None (Direct Top-K) |
| **2. CLIP + Re-ranking** | OpenCLIP ViT-B-32 (`laion2b_s34b_b79k`) | 512 | Cosine / Inner Product | 64-dim HSV Color Histogram |
| **3. ResNet Baseline** | ResNet-50 (`ResNet50_Weights.DEFAULT`) | 2048 | Cosine / Inner Product | None (Direct Top-K) |
| **4. ResNet + Re-ranking** | ResNet-50 (`ResNet50_Weights.DEFAULT`) | 2048 | Cosine / Inner Product | 64-dim HSV Color Histogram |

---

## 3. Comprehensive Empirical Benchmark Comparison

All metrics were computed on stable internal `catalog_item.id`s matching [`data/manifests/catalog_id_map.csv`](file:///d:/visual-product-search/data/manifests/catalog_id_map.csv).

### A. Clean Test Set (200 Queries)

| Pipeline Candidate | Precision@1 | Precision@5 | Precision@10 | Recall@1 | Recall@5 | Recall@10 | Hit@5 | MRR | Total Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CLIP Baseline (Selected)** | **0.2850** | **0.1180** | **0.0725** | **0.2162** | **0.3608** | **0.4286** | **0.4600** | **0.3626** | **141.7 ms** |
| **CLIP + Re-ranking** | **0.2850** | **0.1180** | **0.0725** | **0.2162** | **0.3608** | **0.4286** | **0.4600** | **0.3635** | 138.7 ms |
| **ResNet-50 Baseline** | 0.2350 | 0.0910 | 0.0580 | 0.1716 | 0.2691 | 0.3340 | 0.3800 | 0.3023 | 225.7 ms |
| **ResNet-50 + Re-ranking** | 0.2350 | 0.0910 | 0.0585 | 0.1716 | 0.2691 | 0.3347 | 0.3800 | 0.3029 | 229.8 ms |

### B. Messy Test Set (200 Queries)

| Pipeline Candidate | Precision@1 | Precision@5 | Precision@10 | Recall@1 | Recall@5 | Recall@10 | Hit@5 | MRR | Total Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CLIP Baseline (Selected)** | **0.1300** | **0.0650** | **0.0435** | **0.1013** | **0.2075** | **0.2687** | **0.2750** | **0.1895** | **138.8 ms** |
| **CLIP + Re-ranking** | **0.1300** | **0.0650** | **0.0440** | **0.1013** | **0.2075** | **0.2707** | **0.2750** | **0.1904** | 143.2 ms |
| **ResNet-50 Baseline** | 0.1300 | 0.0590 | 0.0335 | 0.0968 | 0.1760 | 0.2088 | 0.2450 | 0.1769 | 229.5 ms |
| **ResNet-50 + Re-ranking** | 0.1300 | 0.0590 | 0.0335 | 0.0968 | 0.1760 | 0.2088 | 0.2450 | 0.1773 | 222.8 ms |

---

## 4. Messy Robustness Analysis

Evaluating the 8 realistic visual distortion types reveals architectural strengths and weaknesses:

```text
Robustness Ranking by Transformation:
  1. Small Rotation (±8°):       CLIP Hit@5 = 48.0% | ResNet Hit@5 = 36.0% (Minimal degradation)
  2. Darker Lighting (0.65x):     CLIP Hit@5 = 36.0% | ResNet Hit@5 = 32.0% (Strong contrast preservation)
  3. High Contrast (1.50x):       CLIP Hit@5 = 32.0% | ResNet Hit@5 = 32.0% (Moderate impact)
  4. Mild Perspective:           CLIP Hit@5 = 28.0% | ResNet Hit@5 = 36.0% (ResNet slightly more geometric)
  5. Brighter Lighting (1.40x):   CLIP Hit@5 = 28.0% | ResNet Hit@5 = 20.0% (CLIP handles overexposure better)
  6. Tight Crop (10-15%):        CLIP Hit@5 = 28.0% | ResNet Hit@5 = 24.0% (Moderate feature loss)
  7. Background Padding:         CLIP Hit@5 = 12.0% | ResNet Hit@5 = 16.0% (Severe contextual shift)
  8. Defocus Blur (radius 1.5):  CLIP Hit@5 =  8.0% | ResNet Hit@5 =  0.0% (ResNet total failure)
```

---

## 5. System Latency & Operational Feasibility

| Operational Metric | OpenCLIP ViT-B-32 | ResNet-50 | Advantage |
| :--- | :--- | :--- | :--- |
| **Vector Dimension** | **512** | 2048 | **4x Smaller** |
| **Model Parameter Count** | 87.8 M | **25.6 M** | ResNet smaller weights |
| **Model RAM Footprint** | ~340 MB | ~190 MB | Negligible difference |
| **Query Embedding Latency (CPU)** | **135.8 ms** | 145.5 ms | CLIP 7% faster |
| **FAISS Search Latency (44k items)** | **18.9 ms** | 54.2 ms | **CLIP 2.8x faster** |
| **End-to-End Query Latency** | **141.7 ms** | 225.7 ms | **CLIP 37% faster** |
| **Full Vector Catalog Size** | **90.5 MB** | 361.9 MB | **4x Less DB Storage** |

---

## 6. Production Database & pgvector Import Plan

In accordance with the project architecture:
1. **Single Production Model Rule**: Only OpenCLIP 512-dim vectors ([`artifacts/embeddings/clip_embeddings.npy`](file:///d:/visual-product-search/artifacts/embeddings/clip_embeddings.npy)) will be imported into PostgreSQL/SQLite `catalog_items.embedding`.
2. **Experimental ResNet Preservation**: ResNet-50 vectors and indices remain archived in `artifacts/embeddings/resnet_embeddings.npy` and `artifacts/faiss/resnet.index` for benchmarking audits, but will not pollute the production database.
3. **Indexing**: The PostgreSQL column `catalog_items.embedding` will be configured as `VECTOR(512)` with an `HNSW` or `IVFFLAT` cosine index.

---

## 7. Frozen Configuration Specification

The frozen configuration is persisted in [`artifacts/production_model.json`](file:///d:/visual-product-search/artifacts/production_model.json):

```json
{
  "selected_model": {
    "model_name": "OpenCLIP",
    "architecture": "ViT-B-32",
    "pretrained_weights": "laion2b_s34b_b79k",
    "embedding_dimension": 512,
    "similarity_metric": "cosine / inner_product"
  },
  "artifacts": {
    "embeddings_path": "artifacts/embeddings/clip_embeddings.npy",
    "catalog_ids_path": "artifacts/embeddings/clip_catalog_ids.npy",
    "faiss_index_path": "artifacts/faiss/clip.index",
    "faiss_mapping_path": "artifacts/faiss/clip_mapping.csv",
    "production_mapping_path": "artifacts/faiss/production_mapping.csv"
  },
  "database": {
    "target_table": "catalog_items",
    "vector_column": "embedding",
    "vector_dimension": 512
  }
}
```
