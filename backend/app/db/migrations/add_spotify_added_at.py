"""Add spotify_added_at field to tracks table

Revision ID: add_spotify_added_at
Revises: 
Create Date: 2025-11-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_spotify_added_at'
down_revision = None
depends_on = None


def upgrade():
    """Add spotify_added_at column to tracks table"""
    op.add_column('tracks', 
                  sa.Column('spotify_added_at', sa.DateTime(), nullable=True))


def downgrade():
    """Remove spotify_added_at column from tracks table"""
    op.drop_column('tracks', 'spotify_added_at')