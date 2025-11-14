"""Add actual_duration_ms field to library_files table

Revision ID: add_actual_duration_ms
Revises: remove_audio_features
Create Date: 2025-11-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_actual_duration_ms'
down_revision = 'remove_audio_features'
depends_on = None


def upgrade():
    """Add actual_duration_ms column to library_files table"""
    op.add_column('library_files', 
                  sa.Column('actual_duration_ms', sa.Integer(), nullable=True))


def downgrade():
    """Remove actual_duration_ms column from library_files table"""
    op.drop_column('library_files', 'actual_duration_ms')
