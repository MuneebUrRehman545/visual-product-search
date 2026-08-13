# Visual Search Embedding Model Comparison: CLIP ViT-B/32 vs. ResNet-50

This document presents an empirical performance comparison between **CLIP ViT-B/32** and **ResNet-50** feature representations for visual product search. All metrics are derived from executed evaluation runs on the local catalog and query dataset.

---

## 1. Evaluation Setup

- **Catalog Size**: 100 images ingested into SQLite (`data/catalog.db`).
- **Number of Query Images**: 25 evaluation query images.
- **Query Variation Types**: 
  - `different_angle` (5 queries)
  - `different_crop` (4 queries)
  - `changed_lighting` (4 queries)
  - `changed_background` (4 queries)
  - `partially_covered` (4 queries)
  - `phone_camera` (4 queries)
- **Top-k Evaluation Ranks**: $k \in \{1, 5, 10\}$.
- **Ground-Truth Format**: CSV (`data/evaluation/ground_truth.csv`) with schema:
  `query_filename,relevant_product_ids,variation`
  where `relevant_product_ids` maps to SQLite primary key product IDs (pipe-separated `|` for multiple targets).

---

## 2. Models Compared

| Attribute | CLIP ViT-B/32 | ResNet-50 |
| :--- | :--- | :--- |
| **Architecture** | OpenCLIP Vision Transformer (`ViT-B-32`) | `torchvision.models.resnet50` |
| **Pretrained Weights** | `laion2b_s34b_b79k` | `ResNet50_Weights.DEFAULT` |
| **Embedding Dimension** | 512 | 2048 |
| **Feature Extraction** | Image Encoder (`encode_image`) | Sequential layers excluding `fc` classification layer |
| **Similarity Method** | Cosine Similarity (L2-normalized vectors with Inner Product) | Cosine Similarity (L2-normalized vectors with Inner Product) |
| **FAISS Index Type** | `IndexIDMap2(IndexFlatIP)` | `IndexIDMap2(IndexFlatIP)` |

---

## 3. Results Summary Table

| Metric | CLIP (ViT-B/32) | ResNet-50 | Difference (CLIP vs. ResNet) |
| :--- | :--- | :--- | :--- |
| **Precision@1** | **0.9200** | 0.8400 | +0.0800 (+8.0%) |
| **Precision@5** | **0.2000** | 0.1840 | +0.0160 (+1.6%) |
| **Precision@10** | **0.1000** | 0.0960 | +0.0040 (+0.4%) |
| **Recall@1** | **0.9000** | 0.8200 | +0.0800 (+8.0%) |
| **Recall@5** | **0.9800** | 0.9000 | +0.0800 (+8.0%) |
| **Recall@10** | **0.9800** | 0.9400 | +0.0400 (+4.0%) |
| **Average Latency (ms)** | **128.43 ms** | 165.46 ms | -37.03 ms (-22.4%) |
| **Median Latency (ms)** | **119.41 ms** | 148.80 ms | -29.39 ms (-19.8%) |

*Note: Unmeasured metrics such as Mean Reciprocal Rank (MRR) or Normalized Discounted Cumulative Gain (NDCG) were not evaluated in this benchmark and are marked as Not Measured.*

---

## 4. Results by Query Variation

### Precision@5 / Recall@5 & Latency Breakdown by Variation

| Query Variation | Queries | CLIP P@5 / R@5 | ResNet-50 P@5 / R@5 | CLIP Avg Latency (ms) | ResNet-50 Avg Latency (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `changed_background` | 4 | 0.2000 / 1.0000 | 0.2000 / 1.0000 | 134.54 | 202.28 |
| `changed_lighting` | 4 | 0.2000 / 0.8750 | 0.2000 / 0.8750 | 122.64 | 159.74 |
| `different_angle` | 5 | **0.2000 / 1.0000** | 0.2000 / 1.0000 | 129.37 | 170.10 |
| `different_crop` | 4 | 0.2000 / 1.0000 | 0.2000 / 1.0000 | 151.17 | 166.01 |
| `partially_covered` | 4 | 0.2000 / 1.0000 | 0.2000 / 1.0000 | 118.11 | 146.62 |
| `phone_camera` | 4 | **0.2000 / 1.0000** | 0.1000 / 0.5000 | 114.49 | 146.85 |

### Granular Precision@1 Breakdown by Variation

- **`different_angle` (5 queries)**:
  - CLIP Precision@1: **1.0000** (5/5 correct top-1)
  - ResNet-50 Precision@1: **0.6000** (3/5 correct top-1)
- **`phone_camera` (4 queries)**:
  - CLIP Precision@1: **0.5000**, Recall@5: **1.0000**
  - ResNet-50 Precision@1: **0.5000**, Recall@5: **0.5000**
- **`changed_background`, `different_crop`, `partially_covered`**:
  - Both CLIP and ResNet-50 achieved **1.0000 Precision@1**.

---

## 5. Discussion

### Model Accuracy Comparison
CLIP ViT-B/32 outperformed ResNet-50 across all primary accuracy metrics:
- Higher **Precision@1** (0.9200 vs. 0.8400) and **Recall@1** (0.9000 vs. 0.8200).
- Higher **Recall@5** (0.9800 vs. 0.9000).

### Specific Failure Points
- **ResNet-50 Failure under Rotation (`different_angle`)**: ResNet-50 top-1 accuracy dropped to 0.6000 under viewpoint changes, whereas CLIP maintained 1.0000 top-1 accuracy.
- **ResNet-50 Failure under Mobile Degradations (`phone_camera`)**: Under simulated phone camera blur, noise, and color shifts, ResNet-50 Recall@5 dropped to 0.5000 (missing 50% of target items within top 5), whereas CLIP maintained 1.0000 Recall@5.
- **Shared Failures (`changed_lighting`)**: For query `query_003.jpg` (which had multiple relevant items `3|26`), both models retrieved item 3 but did not retrieve item 26 within top-10, resulting in Recall@1..10 of 0.8750 for lighting variations.

### Semantic Similarity vs. Visual Appearance
- **CLIP ViT-B/32**: Learned multimodal representations provide strong robustness to spatial rotations, background context changes, and optical noise.
- **ResNet-50**: Pretrained ImageNet representations capture low-level texture and shape patterns effectively, but suffer degraded top-1 retrieval when objects undergo severe rotation or camera noise.

### Latency and Memory Tradeoffs
- **Vector Storage**: CLIP embeddings require **512 float32 values (2 KB per vector)**, whereas ResNet-50 embeddings require **2048 float32 values (8 KB per vector)**—a **4x storage reduction** for CLIP.
- **Query Latency**: CLIP achieved lower average search latency (**128.43 ms vs. 165.46 ms**) and median search latency (**119.41 ms vs. 148.80 ms**).

---

## 6. Final Decision

### Recommendation
**Recommend CLIP ViT-B/32 (`laion2b_s34b_b79k`) as the primary production search model.**

### Justification Based Strictly on Measured Data
1. **Superior Accuracy**: CLIP delivers **+8.0% higher Precision@1** (0.9200 vs 0.8400) and **+8.0% higher Recall@5** (0.9800 vs 0.9000).
2. **Robustness to Real-World Degradations**: CLIP maintains 1.0000 Recall@5 under phone camera noise (`phone_camera`) and rotation (`different_angle`), compared to ResNet-50's 0.5000 Recall@5 on mobile photos.
3. **Faster Inference Speed**: CLIP query execution is **37.03 ms faster per query on average** (128.43 ms vs 165.46 ms).
4. **4x Compact Embeddings**: 512-dimensional vectors significantly reduce memory footprint and FAISS index size compared to ResNet-50's 2048 dimensions.

---

## 7. Limitations

- **Small Catalog Size**: Evaluated on 100 catalog images. Scalability behavior on millions of items is not measured here.
- **Limited Labeled Query Set**: Benchmark uses 25 query images across 6 synthetic variation types.
- **Manual Ground Truth**: Ground truth relevance labels were assigned based on catalog source items.
- **Unmeasured Scenarios**: Cross-modal text-to-image search, severe low-light conditions, multi-object clutter, and extreme aspect ratio distortions were not explicitly measured.
