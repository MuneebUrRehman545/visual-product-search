-- ============================================================================
-- VERIFICATION SCRIPT: verify_migration.sql
-- DESCRIPTION: Validates presence of new tables, columns, foreign keys, and indexes.
-- ============================================================================

-- 1. Verify existence of all 6 new shared tables
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name IN (
    'pipeline_runs',
    'assets',
    'extracted_data',
    'rag_documents',
    'chat_history',
    'module_events'
  )
ORDER BY table_name;

-- 2. Verify all existing Agent tables remain present and untouched
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name IN (
    'alembic_version',
    'runs',
    'plans',
    'steps',
    'observations',
    'tool_calls',
    'reports'
  )
ORDER BY table_name;

-- 3. Verify additive nullable column on runs table
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'runs'
  AND column_name = 'pipeline_run_id';

-- 4. Verify foreign key constraints for shared integration
SELECT
    tc.table_name, 
    kcu.column_name, 
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    rc.delete_rule
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
  AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
  AND ccu.table_schema = tc.table_schema
JOIN information_schema.referential_constraints AS rc
  ON rc.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
  AND tc.table_schema = 'public'
  AND tc.table_name IN (
    'assets',
    'extracted_data',
    'rag_documents',
    'chat_history',
    'module_events',
    'runs'
  )
ORDER BY tc.table_name, kcu.column_name;

-- 5. Verify index creation
SELECT tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN (
    'idx_assets_pipeline_run_id',
    'idx_extracted_data_pipeline_run_id',
    'idx_rag_documents_pipeline_run_id',
    'idx_chat_history_pipeline_run_id',
    'idx_module_events_pipeline_run_id',
    'idx_runs_pipeline_run_id'
  )
ORDER BY tablename, indexname;
