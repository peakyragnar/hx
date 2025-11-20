"""add requests table and request_id to checks

Revision ID: e2d4f8d9cabc
Revises: d9a3e2f64bfe
Create Date: 2025-02-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e2d4f8d9cabc"
down_revision = "d9a3e2f64bfe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("claim", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=True),
        sa.Column("env", sa.String(length=16), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("anon_token", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_requests_user_id", "requests", ["user_id"])
    op.create_index("ix_requests_anon_env", "requests", ["env", "anon_token"])

    op.add_column("checks", sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        None,
        "checks",
        "requests",
        ["request_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(None, "checks", type_="foreignkey")
    op.drop_column("checks", "request_id")
    op.drop_index("ix_requests_anon_env", table_name="requests")
    op.drop_index("ix_requests_user_id", table_name="requests")
    op.drop_table("requests")
