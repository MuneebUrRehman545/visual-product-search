-- ============================================================================
-- MIGRATION: 002_add_shared_week4_tables.sql
-- DESCRIPTION: Additive Shared Tables for Week 4 (Vision -> RAG -> Agent Pipeline)
-- ENVIRONMENT: Supabase PostgreSQL (Shared AI Assistant)
-- SAFETY: Fully additive. Atomic transaction. NO existing tables dropped. 
--         NO existing Agent foreign keys or data modified.
-- ============================================================================

BEGIN;

-- 1. Create pipeline_runs table (Top-level trace across Vision -> RAG -> Agent)
-- NOTE: status lifecycle is ('created', 'processing', 'completed', 'failed')
-- NOTE: updated_at DEFAULT NOW() sets the creation timestamp; subsequent updates are managed by the application layer.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status VARCHAR(64) NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Create assets table (Multimodal query inputs, e.g. query images)
CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id UUID NOT NULL,
    asset_type VARCHAR(64) NOT NULL DEFAULT 'query_image',
    filename TEXT,
    mime_type VARCHAR(64),
    storage_uri TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_assets_pipeline_run_id FOREIGN KEY (pipeline_run_id) 
        REFERENCES pipeline_runs(id) ON DELETE CASCADE
);

-- 3. Create extracted_data table (Vision structured product search output)
CREATE TABLE IF NOT EXISTS extracted_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id UUID NOT NULL,
    asset_id UUID NULL,
    module VARCHAR(64) NOT NULL DEFAULT 'vision',
    data_type VARCHAR(64) NOT NULL DEFAULT 'visual_product_search_matches',
    content JSONB NOT NULL,
    model VARCHAR(64),
    confidence DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_extracted_data_pipeline_run_id FOREIGN KEY (pipeline_run_id) 
        REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    CONSTRAINT fk_extracted_data_asset_id FOREIGN KEY (asset_id) 
        REFERENCES assets(id) ON DELETE SET NULL
);

-- 4. Create rag_documents table (RAG retrieved context chunks and knowledge)
CREATE TABLE IF NOT EXISTS rag_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id UUID NOT NULL,
    source_extracted_data_id UUID NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_rag_documents_pipeline_run_id FOREIGN KEY (pipeline_run_id) 
        REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    CONSTRAINT fk_rag_documents_source_extracted_id FOREIGN KEY (source_extracted_data_id) 
        REFERENCES extracted_data(id) ON DELETE SET NULL
);

-- 5. Create chat_history table (Conversational message history per pipeline run)
CREATE TABLE IF NOT EXISTS chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id UUID NOT NULL,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_chat_history_pipeline_run_id FOREIGN KEY (pipeline_run_id) 
        REFERENCES pipeline_runs(id) ON DELETE CASCADE
);

-- 6. Create module_events table (Shared multi-module lifecycle audit log)
-- NOTE: event lifecycle includes ('started', 'completed', 'failed')
CREATE TABLE IF NOT EXISTS module_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id UUID NOT NULL,
    module VARCHAR(64) NOT NULL,
    event VARCHAR(64) NOT NULL,
    message TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_module_events_pipeline_run_id FOREIGN KEY (pipeline_run_id) 
        REFERENCES pipeline_runs(id) ON DELETE CASCADE
);

-- 7. Add additive nullable column pipeline_run_id to Moeez's existing runs table (Idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'runs' 
          AND column_name = 'pipeline_run_id'
    ) THEN
        ALTER TABLE runs 
        ADD COLUMN pipeline_run_id UUID NULL;
    END IF;
END $$;

-- 8. Add explicit named foreign key constraint on runs.pipeline_run_id (Idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.table_constraints 
        WHERE table_schema = 'public' 
          AND table_name = 'runs' 
          AND constraint_name = 'fk_runs_pipeline_run_id'
    ) THEN
        ALTER TABLE runs 
        ADD CONSTRAINT fk_runs_pipeline_run_id 
        FOREIGN KEY (pipeline_run_id) 
        REFERENCES pipeline_runs(id) ON DELETE SET NULL;
    END IF;
END $$;

-- 9. Add required indexes for query performance and FK traversals (Idempotent)
CREATE INDEX IF NOT EXISTS idx_assets_pipeline_run_id ON assets(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_extracted_data_pipeline_run_id ON extracted_data(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_rag_documents_pipeline_run_id ON rag_documents(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_pipeline_run_id ON chat_history(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_module_events_pipeline_run_id ON module_events(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_runs_pipeline_run_id ON runs(pipeline_run_id);

COMMIT;
