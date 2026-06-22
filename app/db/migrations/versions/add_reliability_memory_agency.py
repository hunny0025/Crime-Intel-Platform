"""add_reliability_memory_agency

Revision ID: add_reliability_memory_agency
Revises: 
Create Date: 2026-06-22 22:15:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_reliability_memory_agency'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add columns to evidence_artifacts
    op.add_column('evidence_artifacts', sa.Column('acquisition_method', sa.String(length=255), nullable=True))
    op.add_column('evidence_artifacts', sa.Column('composite_reliability_score', sa.Float(), nullable=True))
    
    # Add column to memory_records
    op.add_column('memory_records', sa.Column('memory_tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Add column to cases
    op.add_column('cases', sa.Column('agency_id', postgresql.UUID(as_uuid=True), nullable=True))

    # Create agencies table
    op.create_table('agencies',
        sa.Column('agency_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agency_name', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('agency_id')
    )

    # Create aire_actions table
    op.create_table('aire_actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aire_step', sa.String(length=255), nullable=False),
        sa.Column('action_type', sa.String(length=255), nullable=False),
        sa.Column('target_ref', sa.String(length=255), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reversible', sa.Boolean(), nullable=False),
        sa.Column('reversal_endpoint', sa.String(length=500), nullable=True),
        sa.Column('autonomy_level', sa.String(length=50), nullable=False),
        sa.Column('agency_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.case_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.agency_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('aire_actions')
    op.drop_table('agencies')
    op.drop_column('cases', 'agency_id')
    op.drop_column('memory_records', 'memory_tags')
    op.drop_column('evidence_artifacts', 'composite_reliability_score')
    op.drop_column('evidence_artifacts', 'acquisition_method')
