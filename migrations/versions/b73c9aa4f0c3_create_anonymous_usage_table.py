"""create anonymous usage table

Revision ID: b73c9aa4f0c3
Revises: a1f45b37f4e5
Create Date: 2024-11-06 13:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b73c9aa4f0c3"
down_revision = "a1f45b37f4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "anonymous_usage",
        sa.Column("token", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("checks_allowed", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("checks_used", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_table("anonymous_usage")
