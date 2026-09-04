# Visual Product Search — Evaluation Dataset Specification

## 1. Overview

This directory contains the labeled evaluation dataset specification, query images, ground-truth metadata, and accumulated evaluation results for measuring visual product search model performance across clean and real-world messy conditions.

The evaluation system uses a **zero-leakage split**: all query images and their ground-truth products are strictly excluded from the 44,119-item searchable catalog.

## 2. Directory Structure

```text
evaluation/
├── README.md                      # Dataset specification and labeling guidelines
├── ground_truth.csv               # 200 clean test queries + ground-truth product IDs
├── ground_truth_candidates.csv    # Extended candidate pool used during review
├── ground_truth_review.csv        # Annotated review sheet with quality flags
├── messy_query_manifest.csv       # 200 messy test queries (8 transformation types)
├── queries/                       # Query image files
├── results/                       # Evaluation output files (JSON / CSV)
└── review_sheets/                 # Human-review annotation sheets
```

## 3. Ground-Truth CSV Schema (`ground_truth.csv`)

| Column Name | Type | Description |
| :--- | :--- | :--- |
| `query_id` | String | Unique query identifier (e.g. `q001`, `q002`) |
| `query_image` | String | Relative filepath to the query image (e.g. `evaluation/queries/q001.jpg`) |
| `relevant_product_ids` | String | Comma-separated catalog integer primary keys matching the query |
| `variation_type` | String | Standardized transformation category (see Section 5) |
| `notes` | String | Human-readable descriptor or annotation notes |

## 4. Messy Query Manifest Schema (`messy_query_manifest.csv`)

The messy query manifest contains **200 queries** derived from 8 real-world image transformation types applied to clean catalog images, simulating realistic user-submitted photos.

| Column Name | Type | Description |
| :--- | :--- | :--- |
| `query_id` | String | Unique messy query identifier |
| `query_image` | String | Relative filepath to the transformed query image |
| `relevant_product_ids` | String | Comma-separated catalog integer primary keys |
| `variation_type` | String | Applied transformation type (see Section 5) |
| `source_query_id` | String | Original clean query this was derived from |
| `notes` | String | Transformation description or annotation notes |

## 5. Documented Variation / Transformation Types

| Type | Description |
| :--- | :--- |
| `clean` | Unaltered baseline image matching a catalog item |
| `different_crop` | Cropped or zoomed region of the product |
| `changed_background` | Product isolated on an alternate or neutral background |
| `cluttered_background` | Product placed in a realistic, noisy, or cluttered environment |
| `different_lighting` | Image with altered exposure, shadows, or color balance |
| `partial_object` | Obstructed or partially visible product view |
| `different_angle` | Alternate camera angle or perspective shot |
| `visually_similar` | Visually similar product variant within the same category |
| `phone_camera` | Handheld mobile camera photo of a product |

## 6. Evaluation Metrics

All models are evaluated on the following retrieval metrics at rank cutoff k=1 and k=5:

| Metric | Description |
| :--- | :--- |
| `Precision@1` | Fraction of queries with a relevant item ranked #1 |
| `Precision@5` | Mean fraction of top-5 results that are relevant |
| `Recall@5` | Mean fraction of all relevant items found in top-5 |
| `Hit@5` | Fraction of queries with at least one relevant item in top-5 |
| `MRR` | Mean Reciprocal Rank of the first relevant item |
| `Query Latency` | End-to-end server-side response time per query |

## 7. Running Evaluations

```bash
# Validate evaluation set integrity (schema, file presence, DB ID existence)
python scripts/validate_evaluation_set.py

# Run evaluation against the live search API
python scripts/evaluate_search.py

# Run the complete final evaluation matrix (all models, both test sets)
python scripts/run_final_evaluation.py
```

## 8. Ground-Truth ID Mapping Rules

- **Catalog Primary Keys**: `relevant_product_ids` must contain integer primary key IDs (`id` column) from the catalog database (e.g. `2301`, `2302`).
- **Multiple Relevant Products**: Separate multiple relevant IDs with commas (e.g. `"2301,2322"`).
- **Validation**: Run `python scripts/validate_evaluation_set.py` to verify schema integrity, file presence, and DB ID existence before running any evaluation.

