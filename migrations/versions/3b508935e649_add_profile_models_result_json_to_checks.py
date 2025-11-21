"""add profile models result_json to checks

Revision ID: 3b508935e649
Revises: e2d4f8d9cabc
Create Date: 2025-11-21 17:46:48.367340

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3b508935e649'
down_revision: Union[str, Sequence[str], None] = 'e2d4f8d9cabc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("checks", sa.Column("profile", sa.String(length=32), nullable=True))
    op.add_column("checks", sa.Column("models", postgresql.JSONB(), nullable=True))
    op.add_column("checks", sa.Column("result_json", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("checks", "result_json")
    op.drop_column("checks", "models")
    op.drop_column("checks", "profile")
