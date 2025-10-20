"""add WEL columns to checks table

Revision ID: c23d76c7a8c9
Revises: b73c9aa4f0c3
Create Date: 2025-02-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c23d76c7a8c9"
down_revision = "251c74b4ff73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "checks",
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="baseline"),
    )
    op.add_column("checks", sa.Column("p_prior", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("ci_prior_lo", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("ci_prior_hi", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("stability_prior", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("p_web", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("ci_web_lo", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("ci_web_hi", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("n_docs", sa.Integer(), nullable=True))
    op.add_column("checks", sa.Column("n_domains", sa.Integer(), nullable=True))
    op.add_column("checks", sa.Column("median_age_days", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("web_dispersion", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("json_valid_rate", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("date_confident_rate", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("n_confident_dates", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("p_combined", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("ci_combined_lo", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("ci_combined_hi", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("w_web", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("recency_score", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("strength_score", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("resolved_flag", sa.Boolean(), nullable=True))
    op.add_column("checks", sa.Column("resolved_truth", sa.Boolean(), nullable=True))
    op.add_column("checks", sa.Column("resolved_reason", sa.Text(), nullable=True))
    op.add_column("checks", sa.Column("resolved_support", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("resolved_contradict", sa.Float(), nullable=True))
    op.add_column("checks", sa.Column("resolved_domains", sa.Integer(), nullable=True))
    op.add_column("checks", sa.Column("resolved_citations", sa.Text(), nullable=True))

    # backfill mode for existing rows, then drop server default if not needed
    op.execute("UPDATE checks SET mode = 'baseline' WHERE mode IS NULL")


def downgrade() -> None:
    op.drop_column("checks", "resolved_citations")
    op.drop_column("checks", "resolved_domains")
    op.drop_column("checks", "resolved_contradict")
    op.drop_column("checks", "resolved_support")
    op.drop_column("checks", "resolved_reason")
    op.drop_column("checks", "resolved_truth")
    op.drop_column("checks", "resolved_flag")
    op.drop_column("checks", "strength_score")
    op.drop_column("checks", "recency_score")
    op.drop_column("checks", "w_web")
    op.drop_column("checks", "ci_combined_hi")
    op.drop_column("checks", "ci_combined_lo")
    op.drop_column("checks", "p_combined")
    op.drop_column("checks", "n_confident_dates")
    op.drop_column("checks", "date_confident_rate")
    op.drop_column("checks", "json_valid_rate")
    op.drop_column("checks", "web_dispersion")
    op.drop_column("checks", "median_age_days")
    op.drop_column("checks", "n_domains")
    op.drop_column("checks", "n_docs")
    op.drop_column("checks", "ci_web_hi")
    op.drop_column("checks", "ci_web_lo")
    op.drop_column("checks", "p_web")
    op.drop_column("checks", "stability_prior")
    op.drop_column("checks", "ci_prior_hi")
    op.drop_column("checks", "ci_prior_lo")
    op.drop_column("checks", "p_prior")
    op.drop_column("checks", "mode")
