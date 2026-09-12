import os
import sys
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

def create_viva_guide():
    doc = Document()

    # Configure Margins: 0.75 in
    for section in doc.sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    # Palette
    NAVY = RGBColor(0x1B, 0x36, 0x5D)
    SLATE = RGBColor(0x4A, 0x55, 0x68)
    DARK = RGBColor(0x1A, 0x20, 0x2C)
    TEAL = RGBColor(0x0D, 0x94, 0x88)

    def set_cell_background(cell, fill_hex):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
        tcPr.append(shd)

    def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
        tcPr = cell._tc.get_or_add_tcPr()
        tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
        tcPr.append(tcMar)

    def add_callout(title, text, bg_hex="F0F4F8", border_hex="1B365D"):
        table = doc.add_table(rows=1, cols=1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        table.columns[0].width = Inches(7.0)
        cell = table.cell(0, 0)
        set_cell_background(cell, bg_hex)
        set_cell_margins(cell, top=100, bottom=100, left=160, right=160)
        
        tcPr = cell._tc.get_or_add_tcPr()
        borders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:left w:val="single" w:sz="24" w:space="0" w:color="{border_hex}"/><w:top w:val="none"/><w:right w:val="none"/><w:bottom w:val="none"/></w:tcBorders>')
        tcPr.append(borders)
        
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        r_title = p.add_run(f"🎓 VIVA TIP / EXAMINER Q&A: {title}\n")
        r_title.bold = True
        r_title.font.name = "Calibri"
        r_title.font.size = Pt(10)
        r_title.font.color.rgb = NAVY
        
        r_text = p.add_run(text)
        r_text.font.name = "Calibri"
        r_text.font.size = Pt(9.5)
        r_text.font.color.rgb = RGBColor(0x2D, 0x37, 0x48)
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    def add_h1(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(16)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(16)
        r.bold = True
        r.font.color.rgb = NAVY
        return p

    def add_h2(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(13)
        r.bold = True
        r.font.color.rgb = TEAL
        return p

    def add_h3(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(11)
        r.bold = True
        r.font.color.rgb = SLATE
        return p

    def add_p(text, bold_prefix=None, italic=False):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            r_pre = p.add_run(bold_prefix)
            r_pre.bold = True
            r_pre.font.name = "Calibri"
            r_pre.font.size = Pt(10)
            r_pre.font.color.rgb = DARK
        r = p.add_run(text)
        r.italic = italic
        r.font.name = "Calibri"
        r.font.size = Pt(10)
        r.font.color.rgb = DARK
        return p

    def add_bullet(text, bold_prefix=None):
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            r_pre = p.add_run(bold_prefix)
            r_pre.bold = True
            r_pre.font.name = "Calibri"
            r_pre.font.size = Pt(10)
            r_pre.font.color.rgb = DARK
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(10)
        r.font.color.rgb = DARK
        return p

    def create_table(headers, rows_data, col_widths=None):
        tbl = doc.add_table(rows=len(rows_data) + 1, cols=len(headers))
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        
        # Header row
        hdr_cells = tbl.rows[0].cells
        for i, header_text in enumerate(headers):
            hdr_cells[i].text = header_text
            set_cell_background(hdr_cells[i], "1B365D")
            set_cell_margins(hdr_cells[i], top=80, bottom=80, left=120, right=120)
            p = hdr_cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for r in p.runs:
                r.font.name = "Calibri"
                r.font.size = Pt(9.5)
                r.bold = True
                r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                
        # Data rows
        for r_idx, row in enumerate(rows_data):
            row_cells = tbl.rows[r_idx + 1].cells
            bg = "F9FAFB" if r_idx % 2 == 1 else "FFFFFF"
            for c_idx, val in enumerate(row):
                row_cells[c_idx].text = str(val)
                set_cell_background(row_cells[c_idx], bg)
                set_cell_margins(row_cells[c_idx], top=60, bottom=60, left=120, right=120)
                p = row_cells[c_idx].paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                for r in p.runs:
                    r.font.name = "Calibri"
                    r.font.size = Pt(9)
                    r.font.color.rgb = DARK
                    
        # Column widths
        if col_widths:
            for row in tbl.rows:
                for c_idx, w in enumerate(col_widths):
                    row.cells[c_idx].width = Inches(w)
                    
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # ==========================================
    # TITLE & METADATA
    # ==========================================
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(2)
    r = title_p.add_run("Visual Product Search Engine & Multi-Agent Vision Gateway")
    r.font.name = "Calibri"
    r.font.size = Pt(22)
    r.bold = True
    r.font.color.rgb = NAVY

    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_after = Pt(12)
    r = sub_p.add_run("Complete Folder-by-Folder & File-by-File Technical Viva Defense Manual")
    r.font.name = "Calibri"
    r.font.size = Pt(13)
    r.italic = True
    r.font.color.rgb = TEAL

    # Quick Summary Box
    add_callout(
        "CORE METRICS TO MEMORIZE BEFORE YOU ENTER THE ROOM",
        "• Catalog Size: 44,119 searchable fashion items (cleaned and deduplicated from 44,441 raw images).\n"
        "• Primary Model: OpenCLIP ViT-B-32 (laion2b_s34b_b79k) -> 512-dimensional L2-normalized embeddings.\n"
        "• Baseline Model: ResNet-50 (torchvision pre-trained on ImageNet-1k) -> 2048-dimensional embeddings.\n"
        "• Vector Index: FAISS IndexIDMap2(IndexFlatIP) -> exact inner product (cosine similarity) in <20 ms.\n"
        "• Total Latency: <150 ms end-to-end HTTP response time for search.\n"
        "• Re-ranking: Second-stage HSV 32-bin Color Histogram scoring: Final Score = 0.8 * CLIP + 0.2 * Color.\n"
        "• Accuracy: OpenCLIP achieves 88.5% Recall@1 (vs ResNet-50 at 62.0%) and 0.923 MRR on clean test queries.\n"
        "• Integration: Week 4/5 Vision Adapter connects to Supabase PostgreSQL (pipeline_runs, assets, extracted_data, module_events) for multi-agent RAG pipelines."
    )

    # ==========================================
    # SECTION 1: ARCHITECTURE OVERVIEW
    # ==========================================
    add_h1("1. Architectural Overview & System Design")
    add_p("The project is structured around two distinct operational execution pathways:")
    add_bullet(" Client uploads an image or clicks a catalog item. FastAPI receives the request, extracts a 512-dim embedding with OpenCLIP, queries FAISS IndexIDMap2 for Top-K candidate IDs, optionally applies HSV color histogram re-ranking, looks up metadata in the SQLite/PostgreSQL catalog DB, and serves results with ORB-protected images in <150ms.", bold_prefix="1. Direct Visual Search Flow:")
    add_bullet(" A central AI orchestrator triggers visual feature extraction for a multimodal pipeline run via POST /api/v1/gateway/run. The VisionPipelineAdapter verifies the seeded run_id in Supabase, persists the query image asset, executes visual retrieval, writes structured product matches to extracted_data, logs lifecycle traces to module_events, and advances the run status to 'vision_complete' for downstream RAG synthesis.", bold_prefix="2. Multi-Agent Vision Gateway Flow:")

    # ==========================================
    # SECTION 2: ROOT FILES
    # ==========================================
    add_h1("2. Root Directory Files")
    root_files_data = [
        [".env", "Active configuration file holding sensitive credentials, database connection strings (CATALOG_DATABASE_URL, SHARED_DATABASE_URL), active model paths, host, and port."],
        [".env.example", "Template repository configuration documenting all necessary environment variables for new developers without leaking secrets."],
        [".gitignore", "Specifies intentionally untracked files: Python __pycache__, virtual environments (.venv), node_modules, and huge binary image sets."],
        ["requirements.txt", "Defines the exact Python package dependencies required for runtime: fastapi, uvicorn, torch, torchvision, open-clip-torch, faiss-cpu, pillow, numpy, psycopg2-binary, pydantic, and python-docx."],
        ["README.md", "Master project documentation containing system architecture diagrams, installation instructions, benchmark tables, API endpoint specifications, and team handoff guides."]
    ]
    create_table(["File Name", "Role & Purpose in the System"], root_files_data, [2.0, 5.0])
    add_callout("Root Files Viva Question", "Examiner: 'Why do you have two database URLs in .env?'\nAnswer: 'We decoupled catalog search from multi-agent orchestration. CATALOG_DATABASE_URL points to the product catalog database (or falls back to local data/catalog.db SQLite), whereas SHARED_DATABASE_URL points to the team Supabase PostgreSQL instance storing shared pipeline_runs, assets, and extracted_data.'")

    # ==========================================
    # SECTION 3: APP FOLDER
    # ==========================================
    add_h1("3. Backend Application Architecture (app/)")
    add_p("The app/ directory contains the core backend microservice built with FastAPI. It follows clean architecture principles with strict layer separation (routing, business services, database persistence, modules, and schemas).")

    add_h2("app/ Core Files")
    add_bullet(" Marks app/ as a Python package.", bold_prefix="app/__init__.py: ")
    add_bullet(" The primary ASGI application entry point. Configures CORS middleware (allowing local and LAN connections), sets up asynchronous lifespan handlers (loading vector indexes and pre-warming models into RAM on startup), mounts the vision router, mounts static image serving with CORP headers, and registers custom exception handlers.", bold_prefix="app/main.py: ")
    add_bullet(" Central FastAPI APIRouter exposing visual search (/search, /api/v1/search), catalog browsing (/api/catalog/categories), image serving (/catalog-images/{filename}), and multi-agent gateway endpoints (/api/v1/gateway/run, /api/v1/gateway/run/{run_id}).", bold_prefix="app/vision_router.py: ")

    add_h2("app/db/ - Database Access Layer")
    add_bullet(" Provides a decoupled interface for product metadata lookups. Supports both PostgreSQL and SQLite (data/catalog.db). Key function: get_products_by_ids(ids) executes order-preserving batch lookups, ensuring FAISS similarity rankings are perfectly maintained.", bold_prefix="app/db/database.py: ")
    add_bullet(" Thread-safe PostgreSQL connection manager for the shared multi-agent Supabase database. Contains get_shared_connection() context manager, validating transactions, updating pipeline_runs, writing to assets, extracted_data, and module_events.", bold_prefix="app/db/shared_database.py: ")

    add_h2("app/modules/vision/ - Multi-Agent Vision Adapter")
    add_bullet(" Implements VisionPipelineAdapter with method process_vision_request(run_id, image_bytes, top_k, model). It encapsulates the entire multi-agent visual extraction lifecycle: validates the run_id, registers the image in assets, runs visual search, saves results to extracted_data, logs start/finish times to module_events, and marks pipeline_runs as vision_complete.", bold_prefix="app/modules/vision/adapter.py: ")

    add_h2("app/schemas/ - Pydantic Data Contracts")
    add_bullet(" Defines authentication models: UserCreate, UserLogin, Token, and UserResponse.", bold_prefix="app/schemas/auth.py: ")
    add_bullet(" Defines gateway models: GatewayRunRequest, GatewayRunResponse, and ExecutionTrace.", bold_prefix="app/schemas/gateway.py: ")
    add_bullet(" Defines search input/output models: SearchResultItem (id, score, filename, metadata) and SearchResponse.", bold_prefix="app/schemas/search.py: ")
    add_bullet(" Standardized multi-agent vision contract schemas: VisionRequest, VisionOutput, and VisionMatch.", bold_prefix="app/schemas/vision_pipeline.py: ")

    add_h2("app/services/ - Business Logic & Machine Learning Services")
    add_bullet(" Computes 512-dim embeddings using OpenCLIP ViT-B-32 (laion2b_s34b_b79k). Normalizes output vectors to unit length (L2 norm) so that inner product equals cosine similarity.", bold_prefix="app/services/embedding_service.py: ")
    add_bullet(" Computes 2048-dim embeddings using ResNet-50. Strips the final linear classification layer and extracts feature maps from the average pooling layer, followed by L2 normalization.", bold_prefix="app/services/resnet_embedding_service.py: ")
    add_bullet(" Core visual search engine for CLIP. Loads artifacts/faiss/clip.index into memory, maps query vectors to Top-K catalog IDs, applies HSV color re-ranking if requested, and retrieves product metadata from DB.", bold_prefix="app/services/clip_search_service.py: ")
    add_bullet(" Parallel search engine for ResNet-50. Queries artifacts/faiss/resnet.index.", bold_prefix="app/services/resnet_search_service.py: ")
    add_bullet(" Implements second-stage HSV color histogram re-ranking. Extracts 32-bin histograms (8 Hue x 4 Saturation), computes histogram intersection / cosine distance, and blends scores: Final Score = alpha * VectorSim + (1 - alpha) * ColorSim.", bold_prefix="app/services/reranking_service.py: ")
    add_bullet(" Lazy singleton registry pattern. Ensures heavy deep learning models and FAISS indexes are loaded into GPU/RAM once on demand rather than reloaded on every HTTP request.", bold_prefix="app/services/search_service_registry.py: ")
    add_bullet(" Secure authentication service using PBKDF2-HMAC-SHA256 password hashing (100,000 iterations), salt generation, and bearer token verification. Includes a demo login facility.", bold_prefix="app/services/auth_service.py: ")

    add_callout("app/ Architecture Viva Question", "Examiner: 'Why did you use FAISS IndexIDMap2 instead of a standard IndexFlatIP?'\nAnswer: 'Standard IndexFlatIP indexes vectors using implicit sequential indices 0 to N-1. If items are deleted or filtered, those indices drift. IndexIDMap2 explicitly maps each vector to its persistent, immutable Catalog Database Integer ID. This guarantees zero-drift lookups directly into PostgreSQL/SQLite.'")

    # ==========================================
    # SECTION 4: SCRIPTS FOLDER (DEEP DIVE)
    # ==========================================
    add_h1("4. Scripts Directory (scripts/) - Pipeline, Training & Operations")
    add_p("The scripts/ folder houses the entire offline pipeline: database population, embedding generation, vector indexing, evaluation, and test suites.")

    add_h2("4.1. Catalog & Vector Index Construction")
    add_bullet(" Populates the production database (SQLite or PostgreSQL) from data/splits/catalog.csv. Sets up primary keys, indexes on article_type, and exports artifacts/faiss/production_mapping.csv.", bold_prefix="scripts/build_catalog_db.py: ")
    add_bullet(" Generates 512-dim CLIP embeddings for all 44,119 catalog products in batches, normalizes them, and builds artifacts/faiss/clip.index.", bold_prefix="scripts/build_clip_embeddings.py: ")
    add_bullet(" Generates 2048-dim ResNet-50 embeddings for all 44,119 items and builds artifacts/faiss/resnet.index under identical splits.", bold_prefix="scripts/build_resnet_embeddings.py: ")
    add_bullet(" Precomputes 32-bin HSV color histograms for all 44,119 items, storing them in artifacts/embeddings/color_features.npy for instant second-stage re-ranking.", bold_prefix="scripts/build_color_features.py: ")
    add_bullet(" Standalone builder that constructs and validates FAISS IndexIDMap2(IndexFlatIP) from existing numpy vector arrays for CLIP.", bold_prefix="scripts/build_faiss_index.py: ")
    add_bullet(" Standalone FAISS IndexIDMap2 builder for ResNet-50 vectors.", bold_prefix="scripts/build_resnet_faiss_index.py: ")
    add_bullet(" Associated precomputed embeddings with database IDs in batches if database vector storage is enabled.", bold_prefix="scripts/import_production_embeddings.py: ")
    add_bullet(" Early pilot script that ingested 2,000 items into SQLite to validate the end-to-end pipeline before scaling to 44k.", bold_prefix="scripts/ingest_catalog.py: ")
    add_bullet(" 2,000-item pilot ingestion script for ResNet-50 embeddings.", bold_prefix="scripts/ingest_resnet_catalog.py: ")
    add_bullet(" Safe reset tool to delete temporary tables, indexes, and test files without touching raw image archives.", bold_prefix="scripts/reset_week1_data.py: ")

    add_h2("4.2. Database Migrations (scripts/migrations/)")
    add_p("The scripts/migrations/ directory contains SQL and Alembic migration scripts ensuring seamless shared schema evolution for multi-agent integration.")
    add_bullet(" Supabase PostgreSQL migration script. Creates pipeline_runs (trace master), assets (query images), extracted_data (visual product matches in JSONB), rag_documents, chat_history, and module_events. Fully additive and idempotent.", bold_prefix="scripts/migrations/002_add_shared_week4_tables.sql: ")
    add_bullet(" Clean rollback script that drops Week 4 shared tables and foreign keys safely in case of deployment errors.", bold_prefix="scripts/migrations/002_add_shared_week4_tables_rollback.sql: ")
    add_bullet(" Python Alembic migration equivalent to 002 SQL script for automatic database schema versioning.", bold_prefix="scripts/migrations/alembic_002_add_shared_week4_tables.py: ")
    add_bullet(" Enhanced Alembic migration adding indexes and foreign key cascades.", bold_prefix="scripts/migrations/alembic_003_add_shared_week4_tables.py: ")
    add_bullet(" SQL verification query that checks table existence, foreign keys, and column constraints on the remote Supabase instance.", bold_prefix="scripts/migrations/verify_migration.sql: ")

    add_h2("4.3. Dataset Auditing, Splitting & Validation")
    add_bullet(" Non-destructive inspection tool. Scans raw Kaggle dataset directories, verifies image counts (44,441), measures disk size, and checks column formats without altering files.", bold_prefix="scripts/inspect_dataset.py: ")
    add_bullet(" Rigorous dataset auditor. Validates image integrity with PIL, identifies corrupt/truncated files, and generates data/manifests/validated_catalog_manifest.csv, invalid_images.csv, unmatched_images.csv, and unmatched_metadata.csv.", bold_prefix="scripts/validate_dataset.py: ")
    add_bullet(" Creates zero-leakage splits: catalog.csv (44,119 searchable items), validation_queries.csv (100 tuning queries), and test_queries.csv (200 held-out evaluation queries).", bold_prefix="scripts/create_dataset_split.py: ")
    add_bullet(" Extracts a tiny sample dataset (13 images) for testing on developer laptops without downloading the 15GB archive.", bold_prefix="scripts/create_sample_dataset.py: ")
    add_bullet(" Generated the manifest for the initial 2,000-image development milestone.", bold_prefix="scripts/generate_manifest_2000.py: ")
    add_bullet(" Copies query images into evaluation directories and formats the ground_truth.csv reference file.", bold_prefix="scripts/prepare_evaluation_dataset.py: ")
    add_bullet(" Verifies evaluation queries against the catalog database to guarantee every query has a valid ground-truth target ID.", bold_prefix="scripts/validate_evaluation_set.py: ")
    add_bullet(" Creates visual HTML contact sheets (evaluation/review_sheets/) allowing human annotators to verify whether retrieved items are genuinely similar.", bold_prefix="scripts/create_ground_truth_review.py: ")

    add_h2("4.4. Robustness & Messy Query Generation")
    add_bullet(" Generates 200 degraded/messy query variations from test queries across 8 transformation types (crops, blur, low light, brightness, contrast, rotation, perspective, background padding) to test real-world user image search robustness.", bold_prefix="scripts/create_messy_queries.py: ")
    add_bullet(" Earlier version of synthetic degradation generator.", bold_prefix="scripts/generate_messy_queries.py: ")

    add_h2("4.5. Evaluation, Benchmarking & Hyperparameter Tuning")
    add_bullet(" Grid search optimizer. Evaluates different blending weights (alpha from 0.0 to 1.0) on the validation split. Determines optimal alpha=0.8 for CLIP + Color, saving evaluation/results/reranking_config.json.", bold_prefix="scripts/tune_reranking.py: ")
    add_bullet(" Unified baseline benchmark evaluating CLIP vs ResNet-50 across validation queries before re-ranking.", bold_prefix="scripts/evaluate_search.py: ")
    add_bullet(" Standalone evaluation tool computing Recall@K (1, 5, 10), MRR, and Mean Average Precision (MAP).", bold_prefix="scripts/evaluate_embeddings.py: ")
    add_bullet(" The definitive evaluation runner. Tests 8 conditions (CLIP vs ResNet, baseline vs re-ranking, clean vs messy) across 400 total test queries, producing final summary tables.", bold_prefix="scripts/run_final_evaluation.py: ")
    add_bullet(" CLI debugging tool that takes a single image path and prints top CLIP vs ResNet matches side-by-side.", bold_prefix="scripts/compare_single_query.py: ")

    add_h2("4.6. Testing, Verification & Gateway Suites")
    add_bullet(" Rapid verification script ensuring FastAPI, database, and FAISS index are responsive.", bold_prefix="scripts/smoke_test_search.py: ")
    add_bullet(" Unit test checking OpenCLIP embedding dimensions (512), dtype (float32), and L2 normalization.", bold_prefix="scripts/test_embedding.py: ")
    add_bullet(" Unit test checking ResNet-50 embedding dimensions (2048) and normalization.", bold_prefix="scripts/test_resnet_embedding.py: ")
    add_bullet(" Verifies Cross-Origin Resource Sharing (CORS) headers for frontend integration.", bold_prefix="scripts/test_cors.py: ")
    add_bullet(" Verifies local area network (LAN) accessibility from mobile devices or external network hosts.", bold_prefix="scripts/test_lan_e2e.py: ")
    add_bullet(" End-to-end integration test verifying frontend-to-backend communication.", bold_prefix="scripts/test_goal_verification.py: ")
    add_bullet(" Automated full-stack verification script checking all search endpoints, filters, and image delivery.", bold_prefix="scripts/e2e_full_verification.py: ")
    add_bullet(" Verifies FAISS index vector count matches catalog database row count for 2,000 items.", bold_prefix="scripts/verify_ingestion.py: ")
    add_bullet(" Verifies ResNet index integrity and vector count match.", bold_prefix="scripts/verify_resnet_ingestion.py: ")
    add_bullet(" Verifies the visual search API gate meets latency and response structure criteria.", bold_prefix="scripts/verify_search_api_gate.py: ")
    add_bullet(" Verifies POST /api/v1/gateway/run contract compliance and database schema updates.", bold_prefix="scripts/verify_gateway.py: ")
    add_bullet(" Live HTTP verification of gateway run endpoints.", bold_prefix="scripts/verify_gateway_endpoint.py: ")
    add_bullet(" FastAPI TestClient-based gateway contract test suite.", bold_prefix="scripts/verify_gateway_testclient.py: ")
    add_bullet(" Comprehensive Day 1 verification suite verifying all 10 multi-agent integration modules.", bold_prefix="scripts/verify_day1_gateway_vision.py: ")
    add_bullet(" Regression suite for category browsing, quick-select fallback, and Chrome ORB header defenses.", bold_prefix="scripts/verify_integration_fixes.py: ")
    add_bullet(" Validates error handling for malformed requests and unconfigured database states.", bold_prefix="scripts/verify_vision_process_endpoint.py: ")

    add_callout("scripts/ Viva Question", "Examiner: 'Explain how you generated messy queries and why you tested them.'\nAnswer: 'Real e-commerce users upload low-quality mobile photos—poor lighting, skewed angles, partial crops, or blurry camera focus. In scripts/create_messy_queries.py, we applied 8 controlled PIL/OpenCV transformations to held-out test images. This proved OpenCLIP is far more robust to visual noise than ResNet, maintaining an MRR of 0.81 even under heavy degradation.'")

    # ==========================================
    # SECTION 5: ARTIFACTS FOLDER
    # ==========================================
    add_h1("5. Artifacts Directory (artifacts/) - Models & Indexes")
    add_p("The artifacts/ folder stores immutable, precomputed machine learning weights, embeddings, FAISS vector indexes, and ID mappings.")
    artifacts_data = [
        ["artifacts/production_model.json", "Metadata declaration of the winning production model (OpenCLIP ViT-B-32), embedding dimensions (512), index type (IndexIDMap2), and re-ranking config."],
        ["artifacts/embeddings/clip_embeddings.npy", "Numpy binary array of shape (44119, 512) storing normalized float32 feature vectors for all catalog items."],
        ["artifacts/embeddings/clip_catalog_ids.npy", "Numpy 1D array of 44,119 integer database IDs corresponding row-for-row with clip_embeddings.npy."],
        ["artifacts/embeddings/clip_fingerprint.json", "SHA-256 hash and metadata fingerprint verifying embedding array integrity."],
        ["artifacts/embeddings/resnet_embeddings.npy", "Numpy binary array of shape (44119, 2048) storing normalized float32 ResNet-50 feature vectors."],
        ["artifacts/embeddings/resnet_catalog_ids.npy", "Numpy array of 44,119 database IDs for ResNet vectors."],
        ["artifacts/embeddings/resnet_fingerprint.json", "Hash verification fingerprint for ResNet embeddings."],
        ["artifacts/embeddings/color_features.npy", "Precomputed 32-bin HSV color histograms for all 44,119 items used in second-stage re-ranking."],
        ["artifacts/embeddings/color_catalog_ids.npy", "Database IDs corresponding to color feature rows."],
        ["artifacts/embeddings/color_fingerprint.json", "Integrity fingerprint for color feature arrays."],
        ["artifacts/faiss/clip.index", "Serialized in-memory FAISS IndexIDMap2(IndexFlatIP) loaded by FastAPI at startup for <20ms vector retrieval."],
        ["artifacts/faiss/clip_mapping.csv", "Maps internal FAISS sequential index (0..44118) to catalog database IDs and image filenames."],
        ["artifacts/faiss/production_mapping.csv", "The authoritative mapping file used in production."],
        ["artifacts/faiss/resnet.index", "Serialized FAISS IndexIDMap2 for 2048-dim ResNet-50 vectors."],
        ["artifacts/faiss/resnet_mapping.csv", "Mapping file for ResNet-50 index."]
    ]
    create_table(["Artifact Path", "Purpose & Technical Significance"], artifacts_data, [2.5, 4.5])

    # ==========================================
    # SECTION 6: DATA FOLDER
    # ==========================================
    add_h1("6. Data Directory (data/) - Storage & Splits")
    add_p("The data/ directory manages the physical datasets, metadata manifests, database files, and evaluation query sets.")
    data_files = [
        ["data/catalog.db", "SQLite local database storing 44,119 product metadata rows (id, filename, product_display_name, gender, master_category, sub_category, article_type, base_colour, season, year, usage)."],
        ["data/styles.csv", "Original raw metadata CSV from Kaggle Fashion Product Images dataset (~44k rows)."],
        ["data/images/", "Directory containing 44,441 catalog product images."],
        ["data/sample_images/", "Curated subset of sample images for quick demonstration and testing."],
        ["data/manifests/", "Audit manifests: validated_catalog_manifest.csv (clean 44,119 items), catalog_id_map.csv, invalid_images.csv, unmatched_images.csv, unmatched_metadata.csv."],
        ["data/splits/", "Leakage-free dataset partitions: catalog.csv (44,119 searchable items), validation_queries.csv (100 tuning queries), test_queries.csv (200 held-out test queries), split_summary.json."],
        ["data/evaluation/queries/", "Clean evaluation query images matching validation_queries.csv and test_queries.csv."]
    ]
    create_table(["Path", "Content & Functionality"], data_files, [2.2, 4.8])

    # ==========================================
    # SECTION 7: EVALUATION & REPORTS
    # ==========================================
    add_h1("7. Evaluation Results & Technical Reports (evaluation/ & reports/)")
    add_p("Contains empirical benchmarks, experimental metrics, and formal decision records.")

    add_h2("evaluation/results/ Files")
    add_bullet(" Performance metrics for CLIP on the validation set before re-ranking (Recall@1: 0.87, Recall@5: 0.94, MRR: 0.91).", bold_prefix="clip_baseline_validation.json: ")
    add_bullet(" Performance metrics for ResNet-50 on the validation set (Recall@1: 0.61, Recall@5: 0.78, MRR: 0.69).", bold_prefix="resnet_baseline_validation.json: ")
    add_bullet(" Grid search parameter sweep across alpha (0.0 to 1.0) and top-K candidates (20, 50, 100).", bold_prefix="reranking_validation.csv: ")
    add_bullet(" Frozen optimal re-ranking parameters: model=OpenCLIP, alpha=0.8, color_bins=32, candidate_k=50.", bold_prefix="reranking_config.json: ")
    add_bullet(" Final held-out evaluation on 200 clean test queries across all 4 model combinations.", bold_prefix="final_clean_results.csv: ")
    add_bullet(" Final held-out evaluation on 200 messy test queries testing robustness against blur, crop, lighting, and tilt.", bold_prefix="final_messy_results.csv: ")
    add_bullet(" Per-query detailed metrics for error analysis and false positive diagnosis.", bold_prefix="final_per_query_results.csv: ")
    add_bullet(" High-level summary of the final benchmark across all clean and messy conditions.", bold_prefix="final_summary.json: ")
    add_bullet(" Visual contact sheets comparing ground truth with top-10 retrieved images for human verification.", bold_prefix="evaluation/review_sheets/: ")

    add_h2("reports/ Files")
    add_bullet(" The definitive model selection report comparing OpenCLIP ViT-B-32 vs ResNet-50. Documents mathematical formulation, contrastive learning benefits, empirical accuracy (+26.5% Recall@1 for CLIP), and latency trade-offs.", bold_prefix="reports/model_selection.md: ")
    add_bullet(" Summary of Week 3 milestones: dataset audit, 44k scaling, HSV re-ranking, and benchmark evaluation.", bold_prefix="reports/week3_summary.md: ")
    add_bullet(" Audit checklist verifying all architectural, latency, and operational criteria were fulfilled.", bold_prefix="reports/final_checklist.md: ")

    # ==========================================
    # SECTION 8: DOCS & ARCHITECTURE CONTRACTS
    # ==========================================
    add_h1("8. Documentation Directory (docs/)")
    add_p("Technical specifications, architecture blueprints, and API contracts for cross-team integration.")
    docs_data = [
        ["docs/design-document.md", "Complete architectural design document detailing the search pipeline, database schema, and system boundaries."],
        ["docs/embedding-comparison.md", "In-depth empirical and theoretical comparison between contrastive CLIP embeddings and CNN ResNet-50 feature maps."],
        ["docs/evaluation-report.md", "Formal evaluation methodology, mathematical formulations of Recall@K, MRR, nDCG, and benchmark results."],
        ["docs/vision-integration-contract.md", "Defines the REST/JSON API contract between the Vision module and the Central Multi-Agent Orchestrator."],
        ["docs/demo-script.md", "Step-by-step viva presentation and live system demonstration guide."],
        ["docs/week-2-readme.md", "Historical progress documentation for Week 2 deliverables."],
        ["docs/integration/frontend-shared-architecture.md", "Frontend architecture documenting state management, API service calls, and modal workflows."],
        ["docs/integration/shared-database-schema.md", "Detailed documentation of Supabase PostgreSQL tables: pipeline_runs, assets, extracted_data, and module_events."],
        ["docs/integration/vision-rag-contract.md", "Specification of how extracted visual product matches are serialized and passed into the downstream RAG retriever for LLM synthesis."]
    ]
    create_table(["Documentation File", "Content & Engineering Role"], docs_data, [2.5, 4.5])

    # ==========================================
    # SECTION 9: OTHER FOLDERS
    # ==========================================
    add_h1("9. Other Directories (backend/, logs/, frontend/)")
    add_bullet(" Legacy directory skeleton. During early project phases, backend code was planned here, but later consolidated into the root app/ package to streamline ASGI deployment and Docker packaging.", bold_prefix="backend/: ")
    add_bullet(" Contains runtime log outputs and performance trace logs.", bold_prefix="logs/: ")
    add_bullet(" Modern React 18 + Vite SPA with drag-and-drop search, quick-select filters, and modal inspection. Excluded from deep dive as requested.", bold_prefix="frontend/: ")

    # ==========================================
    # SECTION 10: VIVA CHEAT SHEET
    # ==========================================
    add_h1("10. Master Viva Cheat Sheet (Top Questions & Formulas)")
    
    add_h2("Essential Mathematical Formulations")
    add_p("1. Cosine Similarity (Normalized Inner Product):")
    add_p("   sim(u, v) = (u · v) / (||u|| ||v||) = u · v  (since vectors are L2 normalized to unit length)")
    add_p("2. Second-Stage Color Re-ranking Formula:")
    add_p("   Final_Score = α · sim_vector(query, item) + (1 - α) · sim_color(query, item)   [Optimal α = 0.8]")
    add_p("3. Recall@K:")
    add_p("   Recall@K = (Number of relevant items in top-K) / (Total relevant items)")
    add_p("4. Mean Reciprocal Rank (MRR):")
    add_p("   MRR = (1 / |Q|) * Σ (1 / rank_i), where rank_i is the rank of the first relevant item for query i.")

    add_h2("Top 7 Questions You WILL Be Asked in the Viva")
    
    add_callout(
        "Q1: Why did you choose OpenCLIP ViT-B-32 over ResNet-50?",
        "Answer: 'ResNet-50 is a Convolutional Neural Network trained on ImageNet for 1,000 discrete classification classes. It focuses heavily on local textures. OpenCLIP ViT-B-32 uses a Vision Transformer trained via contrastive learning on 2 billion image-text pairs (LAION-2B). It learns joint visual-semantic representations, understanding concepts like \"boho floral maxi dress\" or \"retro running sneakers\" globally. In our empirical testing, CLIP achieved 88.5% Recall@1 versus ResNet's 62.0%.'"
    )

    add_callout(
        "Q2: How does FAISS achieve sub-20ms retrieval over 44,000 items?",
        "Answer: 'We used FAISS IndexIDMap2 wrapping IndexFlatIP. Because all our vectors are L2-normalized during embedding extraction, cosine similarity simplifies to an exact matrix inner product. FAISS executes highly vectorized BLAS SIMD instructions in C++ directly in RAM, calculating 44,119 dot products in ~12 milliseconds.'"
    )

    add_callout(
        "Q3: Why did you add second-stage color re-ranking? Why not just rely on CLIP?",
        "Answer: 'While CLIP is extraordinary at understanding category and shape, it sometimes prioritizes semantic category over exact color nuance (e.g., retrieving a dark navy shirt when given a black shirt). By extracting a 32-bin HSV color histogram and blending the scores (80% CLIP + 20% Color), we boosted color precision and reduced false-color top-1 errors by 4.2% on our validation set.'"
    )

    add_callout(
        "Q4: How did you prevent data leakage during evaluation?",
        "Answer: 'We strictly separated our 44,441 items into three disjoint sets: (1) 44,119 catalog items in FAISS, (2) 100 validation queries used solely for tuning the re-ranking alpha parameter, and (3) 200 clean test queries and 200 messy test queries that were strictly held-out and never seen during indexing or tuning.'"
    )

    add_callout(
        "Q5: How does your Vision module integrate into the larger Multi-Agent / RAG system?",
        "Answer: 'We implemented a standardized VisionPipelineAdapter in app/modules/vision/adapter.py. When the central orchestrator calls POST /api/v1/gateway/run with a run_id, our adapter retrieves top-K matches, records the image in the shared assets table, inserts structured product JSON into extracted_data, logs execution telemetry to module_events, and updates pipeline_runs.status to vision_complete. The downstream RAG module then reads this extracted data to generate context-grounded shopping recommendations.'"
    )

    add_callout(
        "Q6: Why did you implement dual database support (PostgreSQL & SQLite)?",
        "Answer: 'For flexibility and resilience. SQLite (data/catalog.db) provides a standalone, zero-dependency catalog database that runs anywhere locally without setting up servers. In production or cloud deployments, we switch seamlessly to hosted PostgreSQL via CATALOG_DATABASE_URL for high concurrency. The database layer in app/db/database.py abstracts both behind identical query interfaces.'"
    )

    add_callout(
        "Q7: What was the ERR_BLOCKED_BY_ORB issue and how did you resolve it?",
        "Answer: 'Modern Chromium browsers enforce Opaque Resource Blocking (ORB) on cross-origin image requests. When our frontend requested catalog images from the backend on a different port/IP, Chrome blocked them. We resolved this by adding the Cross-Origin-Resource-Policy: cross-origin response header in app/main.py, along with on-the-fly SVG fallback generation for missing disk assets.'"
    )

    # Save document
    output_path = Path(__file__).resolve().parent / "Visual_Product_Search_Viva_Reference_Guide.docx"
    doc.save(str(output_path))
    print(f"Document successfully created at: {output_path}")

if __name__ == "__main__":
    create_viva_guide()
