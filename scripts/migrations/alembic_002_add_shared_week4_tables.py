"""Add shared Week 4 integration tables (pipeline_runs, assets, extracted_data, rag_documents, chat_history, module_events)

Revision ID: 002_add_shared_week4_tables
Revises: 
Create Date: 2026-08-28 18:25:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_shared_week4_tables'
down_revision = None  # Align with latest revision in Moeez's Alembic chain
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create pipeline_runs table
    op.create_table(
        'pipeline_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('status', sa.String(length=64), server_default='started', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. Create assets table
    op.create_table(
        'assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('pipeline_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('asset_type', sa.String(length=64), server_default='query_image', nullable=False),
        sa.Column('filename', sa.Text(), nullable=True),
        sa.Column('mime_type', sa.String(length=64), nullable=True),
        sa.Column('storage_uri', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['pipeline_run_id'], ['pipeline_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_assets_pipeline_run_id', 'assets', ['pipeline_run_id'], unique=False)

    # 3. Create extracted_data table
    op.create_table(
        'extracted_data',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('pipeline_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('module', sa.String(length=64), server_default='vision', nullable=False),
        sa.Column('data_type', sa.String(length=64), server_default='visual_product_search_matches', nullable=False),
        sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['pipeline_run_id'], ['pipeline_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_extracted_data_pipeline_run_id', 'extracted_data', ['pipeline_run_id'], unique=False)

    # 4. Create rag_documents table
    op.create_table(
        'rag_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('pipeline_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_extracted_data_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['pipeline_run_id'], ['pipeline_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_extracted_data_id'], ['extracted_data.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_rag_documents_pipeline_run_id', 'rag_documents', ['pipeline_run_id'], unique=False)

    # 5. Create chat_history table
    op.create_table(
        'chat_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('pipeline_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['pipeline_run_id'], ['pipeline_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_chat_history_pipeline_run_id', 'chat_history', ['pipeline_run_id'], unique=False)

    # 6. Create module_events table
    op.create_table(
        'module_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('pipeline_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('module', sa.String(length=64), nullable=False),
        sa.Column('event', sa.String(length=64), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['pipeline_run_id'], ['pipeline_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_module_events_pipeline_run_id', 'module_events', ['pipeline_run_id'], unique=False)

    # 7. Add nullable pipeline_run_id column to existing runs table
    op.add_column('runs', sa.Column('pipeline_run_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_runs_pipeline_run_id',
        'runs',
        'pipeline_runs',
        ['pipeline_run_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('idx_runs_pipeline_run_id', 'runs', ['pipeline_run_id'], unique=False)


def downgrade() -> None:
    # 1. Remove column and FK from runs
    op.drop_index('idx_runs_pipeline_run_id', table_name='runs')
    op.drop_constraint('fk_runs_pipeline_run_id', 'runs', type_='foreignkey')
    op.drop_column('runs', 'pipeline_run_id')

    # 2. Drop new shared tables
    op.drop_index('idx_module_events_pipeline_run_id', table_name='module_events')
    op.drop_table('module_events')

    op.drop_index('idx_chat_history_pipeline_run_id', table_name='chat_history')
    op.drop_table('chat_history')

    op.drop_index('idx_rag_documents_pipeline_run_id', table_name='rag_documents')
    op.drop_table('rag_documents')

    op.drop_index('idx_extracted_data_pipeline_run_id', table_name='extracted_data')
    op.drop_table('extracted_data')

    op.drop_index('idx_assets_pipeline_run_id', table_name='assets')
    op.drop_table('assets')

    op.drop_table('pipeline_runs')
