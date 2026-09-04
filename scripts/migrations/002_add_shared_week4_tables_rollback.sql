-- ============================================================================
-- ROLLBACK SCRIPT: 002_add_shared_week4_tables_rollback.sql
-- DESCRIPTION: Reverses migration 002_add_shared_week4_tables.sql safely.
-- SAFETY: Drops only Week 4 additive tables and columns. Preserves existing Agent data.
-- ============================================================================

BEGIN;

-- 1. Remove additive column from existing runs table
ALTER TABLE IF EXISTS runs DROP COLUMN IF EXISTS pipeline_run_id;

-- 2. Drop new shared tables in reverse dependency order
DROP TABLE IF EXISTS module_events CASCADE;
DROP TABLE IF EXISTS chat_history CASCADE;
DROP TABLE IF EXISTS rag_documents CASCADE;
DROP TABLE IF EXISTS extracted_data CASCADE;
DROP TABLE IF EXISTS assets CASCADE;
DROP TABLE IF EXISTS pipeline_runs CASCADE;

COMMIT;
