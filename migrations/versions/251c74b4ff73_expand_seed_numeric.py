"""expand seed numeric range

Revision ID: 251c74b4ff73
Revises: b73c9aa4f0c3
Create Date: 2025-09-25 15:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "251c74b4ff73"
down_revision: Union[str, Sequence[str], None] = "b73c9aa4f0c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BIGINT_MIN = -9223372036854775808
BIGINT_MAX = 9223372036854775807


def upgrade() -> None:
    """Expand seed columns to hold unsigned 64-bit values."""
    op.alter_column(
        "checks",
        "seed",
        existing_type=sa.BigInteger(),
        type_=sa.Numeric(20, 0),
        existing_nullable=True,
        postgresql_using="seed::numeric",
    )
    op.alter_column(
        "checks",
        "bootstrap_seed",
        existing_type=sa.BigInteger(),
        type_=sa.Numeric(20, 0),
        existing_nullable=True,
        postgresql_using="bootstrap_seed::numeric",
    )


def downgrade() -> None:
    """Restore seed columns to BIGINT with clamped casting."""
    clamp_expr = (
        "CASE "
        "WHEN seed IS NULL THEN NULL "
        f"WHEN seed < {BIGINT_MIN} THEN {BIGINT_MIN} "
        f"WHEN seed > {BIGINT_MAX} THEN {BIGINT_MAX} "
        "ELSE seed::bigint END"
    )
    op.alter_column(
        "checks",
        "seed",
        existing_type=sa.Numeric(20, 0),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using=clamp_expr,
    )
    clamp_bootstrap = (
        "CASE "
        "WHEN bootstrap_seed IS NULL THEN NULL "
        f"WHEN bootstrap_seed < {BIGINT_MIN} THEN {BIGINT_MIN} "
        f"WHEN bootstrap_seed > {BIGINT_MAX} THEN {BIGINT_MAX} "
        "ELSE bootstrap_seed::bigint END"
    )
    op.alter_column(
        "checks",
        "bootstrap_seed",
        existing_type=sa.Numeric(20, 0),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using=clamp_bootstrap,
    )
