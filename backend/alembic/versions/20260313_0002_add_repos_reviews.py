"""add repos and reviews tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("github_repo_id", sa.Integer(), nullable=False),
        sa.Column("repo_name", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_repos_github_repo_id", "repos", ["github_repo_id"], unique=True)

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("repo_id", sa.Integer(), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("code_snippet", sa.String(), nullable=False),
        sa.Column("findings_json", sa.String(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reviews_repo_id", "reviews", ["repo_id"], unique=False)


def downgrade() -> None:
    # Drop reviews first due to FK dependency on repos
    op.drop_index("ix_reviews_repo_id", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_repos_github_repo_id", table_name="repos")
    op.drop_table("repos")
