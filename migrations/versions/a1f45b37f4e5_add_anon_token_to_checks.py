"""add anon token to checks

Revision ID: a1f45b37f4e5
Revises: bf9108335f49_add_stripe_customer_fields
Create Date: 2024-11-06 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1f45b37f4e5"
down_revision = "bf9108335f49"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("checks", sa.Column("anon_token", sa.String(length=64), nullable=True))
    op.create_index("ix_checks_env_anon_token", "checks", ["env", "anon_token"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_checks_env_anon_token", table_name="checks")
    op.drop_column("checks", "anon_token")
