"""add provider metadata to checks

Revision ID: d9a3e2f64bfe
Revises: c23d76c7a8c9
Create Date: 2025-11-13 19:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d9a3e2f64bfe"
down_revision = "c23d76c7a8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("checks", sa.Column("provider", sa.String(length=32), nullable=True))
    op.add_column("checks", sa.Column("logical_model", sa.String(length=64), nullable=True))
    op.add_column("checks", sa.Column("schema_version", sa.String(length=32), nullable=True))
    op.add_column("checks", sa.Column("tokens_in", sa.BigInteger(), nullable=True))
    op.add_column("checks", sa.Column("tokens_out", sa.BigInteger(), nullable=True))
    op.add_column("checks", sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("checks", "cost_usd")
    op.drop_column("checks", "tokens_out")
    op.drop_column("checks", "tokens_in")
    op.drop_column("checks", "schema_version")
    op.drop_column("checks", "logical_model")
    op.drop_column("checks", "provider")
