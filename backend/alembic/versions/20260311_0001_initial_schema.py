"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-11

"""
from typing import Sequence, Union

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Phase 1: No tables yet.
    # Phase 2 will add the next migration revision for reviews + repos tables.
    # This migration establishes the baseline Alembic revision.
    pass


def downgrade() -> None:
    pass
