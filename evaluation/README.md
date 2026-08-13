# Visual Product Search — Evaluation Dataset Specification

## 1. Overview

This directory contains the labeled evaluation dataset specification, query images, and ground-truth metadata for evaluating visual product search model performance.

## 2. Directory Structure

```text
evaluation/
├── ground_truth.csv        # Ground truth mappings and category variations
├── README.md               # Dataset specification and labeling guidelines
└── queries/                # Query image files (q001.jpg .. q025.jpg)
```

## 3. Ground-Truth CSV Schema (`ground_truth.csv`)

| Column Name | Type | Description |
| :--- | :--- | :--- |
| `query_id` | String | Unique query identifier (e.g. `q001`, `q002`) |
| `query_image` | String | Relative filepath to the query image on disk (e.g. `evaluation/queries/q001.jpg`) |
| `relevant_product_ids` | String | Comma-separated SQLite integer primary keys (`products.id`) matching the query |
| `variation_type` | String | Standardized transformation category |
| `notes` | String | Human-readable descriptor or notes |

## 4. Documented Variation Categories (`variation_type`)

1. `clean`: Unaltered baseline image matching catalog item.
2. `different_crop`: Cropped or zoomed region of the product.
3. `changed_background`: Isolated product placed on an alternate background.
4. `cluttered_background`: Product placed in a realistic, noisy, or cluttered environment.
5. `different_lighting`: Image with altered exposure, shadows, or color balance.
6. `partial_object`: Obstructed or partially visible product view.
7. `different_angle`: Alternate camera angle or perspective.
8. `visually_similar`: Visually similar product variant within the same category.
9. `phone_camera`: Handheld mobile camera photo query.

## 5. Ground Truth ID Mapping Rules

* **SQLite Primary Keys**: `relevant_product_ids` must contain actual integer primary key IDs (`products.id`) from `data/catalog.db` (e.g. `2301`, `2302`).
* **Multiple Relevant Products**: If a query image matches multiple catalog items, separate their integer IDs with commas (e.g. `"2301,2322"`).
* **Validation**: Run `python scripts/validate_evaluation_set.py` to verify schema integrity, file presence, and DB ID existence.
