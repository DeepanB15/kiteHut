from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import declarative_base
import uuid
from datetime import datetime

revision = '001_initial'
branch_labels = None
depends_on = None


def _uuid_str():
    return lambda: str(uuid.uuid4())


def upgrade():
    # Create all tables matching models.py
    # Using direct SQL for simplicity since Alembic config is minimal
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.create_table(
        'repositories',
        sa.Column('id', sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4())),
        sa.Column('name', sa.String(512), nullable=False),
        sa.Column('path', sa.String(4096), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        sa.Column('last_indexed_at', sa.DateTime, nullable=True),
        sa.Column('status', sa.String(32), default='idle'),
        sa.Column('total_files', sa.Integer, default=0),
        sa.Column('total_symbols', sa.Integer, default=0),
        sa.Column('error_message', sa.Text, nullable=True),
    )
    op.create_table(
        'files',
        sa.Column('id', sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4())),
        sa.Column('repository_id', sa.String(36), sa.ForeignKey('repositories.id'), nullable=False),
        sa.Column('path', sa.String(1024), nullable=False),
        sa.Column('language', sa.String(64), nullable=False),
        sa.Column('symbol_count', sa.Integer, default=0),
        sa.Column('is_test', sa.Boolean, default=False),
        sa.Column('parent_dir', sa.String(512), nullable=True),
        sa.Column('line_count', sa.Integer, default=0),
    )
    op.create_index('ix_repo_file', 'files', ['repository_id', 'path'])
    op.create_table(
        'symbols',
        sa.Column('id', sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4())),
        sa.Column('repository_id', sa.String(36), sa.ForeignKey('repositories.id'), nullable=False),
        sa.Column('symbol_type', sa.String(32), nullable=False),
        sa.Column('name', sa.String(512), nullable=False),
        sa.Column('file_path', sa.String(1024), nullable=False),
        sa.Column('line_start', sa.Integer, nullable=True),
        sa.Column('line_end', sa.Integer, nullable=True),
        sa.Column('qualified_name', sa.String(1024), nullable=True),
        sa.Column('module_path', sa.String(1024), nullable=True),
    )
    op.create_index('ix_sym_repo_name', 'symbols', ['repository_id', 'name'])
    op.create_table(
        'relationships',
        sa.Column('id', sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4())),
        sa.Column('repository_id', sa.String(36), sa.ForeignKey('repositories.id'), nullable=False),
        sa.Column('source_symbol_id', sa.String(36), sa.ForeignKey('symbols.id'), nullable=False),
        sa.Column('target_symbol_id', sa.String(36), sa.ForeignKey('symbols.id'), nullable=False),
        sa.Column('relationship_type', sa.String(64), nullable=False),
        sa.Column('evidence_ref', JSON, nullable=True),
    )
    op.create_index('ix_rels_pair', 'relationships', ['source_symbol_id', 'target_symbol_id', 'relationship_type'])
    op.create_table(
        'findings',
        sa.Column('id', sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4())),
        sa.Column('repository_id', sa.String(36), sa.ForeignKey('repositories.id'), nullable=False),
        sa.Column('category', sa.String(64), nullable=False),
        sa.Column('severity', sa.String(32), nullable=False),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('confidence', sa.String(32), default='MEDIUM'),
        sa.Column('evidence_refs', JSON, nullable=True),
        sa.Column('intent_category', sa.String(32), nullable=True),
        sa.Column('ai_provider', sa.String(128), nullable=True),
        sa.Column('timestamp', sa.DateTime, default=datetime.utcnow),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.Column('status', sa.String(32), default='OPEN'),
        sa.Column('fix_proposal', JSON, nullable=True),
    )
    op.create_index('ix_findings_cat', 'findings', ['repository_id', 'category'])
    op.create_table(
        'fix_proposals',
        sa.Column('id', sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4())),
        sa.Column('finding_id', sa.String(36), sa.ForeignKey('findings.id'), nullable=False),
        sa.Column('status', sa.String(32), default='proposed'),
        sa.Column('patch_diff', sa.Text, nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('affected_files', JSON, nullable=True),
        sa.Column('test_output', sa.Text, nullable=True),
        sa.Column('verification_result', JSON, nullable=True),
        sa.Column('reviewed_by', sa.String(128), nullable=True),
        sa.Column('comment', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    )


def downgrade():
    op.drop_table('fix_proposals')
    op.drop_table('findings')
    op.drop_table('relationships')
    op.drop_table('symbols')
    op.drop_table('files')
    op.drop_table('repositories')
