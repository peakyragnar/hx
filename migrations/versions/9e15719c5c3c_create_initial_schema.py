"""create initial schema

Revision ID: 9e15719c5c3c
Revises: 
Create Date: 2025-09-17 15:24:55.719565

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9e15719c5c3c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False, server_default="trial"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "usage_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False),
        sa.Column("checks_allowed", sa.Integer(), nullable=False),
        sa.Column("checks_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "period_start", name="uq_usage_period"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "email_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selector", sa.String(length=64), nullable=False),
        sa.Column("verifier_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("selector", name="uq_email_tokens_selector"),
    )

    op.create_table(
        "checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("env", sa.String(length=16), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim", sa.Text(), nullable=True),
        sa.Column("claim_hash", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("K", sa.Integer(), nullable=False),
        sa.Column("R", sa.Integer(), nullable=False),
        sa.Column("T", sa.Integer(), nullable=True),
        sa.Column("B", sa.Integer(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("bootstrap_seed", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("prob_true_rpl", sa.Float(), nullable=True),
        sa.Column("ci_lo", sa.Float(), nullable=True),
        sa.Column("ci_hi", sa.Float(), nullable=True),
        sa.Column("ci_width", sa.Float(), nullable=True),
        sa.Column("template_iqr_logit", sa.Float(), nullable=True),
        sa.Column("stability_score", sa.Float(), nullable=True),
        sa.Column("imbalance_ratio", sa.Float(), nullable=True),
        sa.Column("rpl_compliance_rate", sa.Float(), nullable=True),
        sa.Column("cache_hit_rate", sa.Float(), nullable=True),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("sampler_json", sa.Text(), nullable=True),
        sa.Column("counts_by_template_json", sa.Text(), nullable=True),
        sa.Column("artifact_json_path", sa.Text(), nullable=True),
        sa.Column("prompt_char_len_max", sa.Integer(), nullable=True),
        sa.Column("pqs", sa.Float(), nullable=True),
        sa.Column("gate_compliance_ok", sa.Boolean(), nullable=True),
        sa.Column("gate_stability_ok", sa.Boolean(), nullable=True),
        sa.Column("gate_precision_ok", sa.Boolean(), nullable=True),
        sa.Column("pqs_version", sa.String(length=32), nullable=True),
        sa.Column("was_cached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("provider_model_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_checks_run_id"),
    )

    op.create_table(
        "result_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_key", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("env", sa.String(length=16), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("result_key", name="uq_result_cache_key"),
    )

    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_index("ix_email_tokens_user_id", "email_tokens", ["user_id"], unique=False)
    op.create_index("ix_checks_user_id", "checks", ["user_id"], unique=False)
    op.create_index("ix_checks_env", "checks", ["env"], unique=False)
    op.create_index("ix_checks_claim_hash", "checks", ["claim_hash"], unique=False)
    op.create_index("ix_usage_user", "usage_ledger", ["user_id"], unique=False)
    op.create_index("ix_result_cache_env", "result_cache", ["env"], unique=False)
    op.create_index("ix_result_cache_user", "result_cache", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_result_cache_user", table_name="result_cache")
    op.drop_index("ix_result_cache_env", table_name="result_cache")
    op.drop_table("result_cache")

    op.drop_index("ix_checks_claim_hash", table_name="checks")
    op.drop_index("ix_checks_env", table_name="checks")
    op.drop_index("ix_checks_user_id", table_name="checks")
    op.drop_table("checks")

    op.drop_index("ix_email_tokens_user_id", table_name="email_tokens")
    op.drop_table("email_tokens")

    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_usage_user", table_name="usage_ledger")
    op.drop_table("usage_ledger")

    op.drop_table("users")
