"""user preferred language

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("preferred_language", sa.String(8), nullable=False, server_default="en"))


def downgrade() -> None:
    op.drop_column("users", "preferred_language")
