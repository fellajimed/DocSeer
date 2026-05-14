"""Initial schema – papers table.

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Create the enum type first
    paperstatus = postgresql.ENUM(
        "pending",
        "processing",
        "done",
        "failed",
        "metadata_only",
        name="paperstatus",
    )
    paperstatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "papers",
        # ── identity ──────────────────────────────────────────────────────────
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # ── source ────────────────────────────────────────────────────────────
        sa.Column("source_path", sa.Text, nullable=True, unique=True),
        # ── bibliographic ─────────────────────────────────────────────────────
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("authors", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("abstract", sa.Text, nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("journal", sa.Text, nullable=True),
        sa.Column("publisher", sa.Text, nullable=True),
        sa.Column("doi", sa.Text, nullable=True),
        sa.Column("arxiv_id", sa.Text, nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("isbn", sa.Text, nullable=True),
        # ── zotero / bibtex ───────────────────────────────────────────────────
        sa.Column("bibtex_key", sa.Text, nullable=True),
        sa.Column("bibtex_raw", sa.Text, nullable=True),
        sa.Column("zotero_key", sa.Text, nullable=True),
        sa.Column("collection", sa.Text, nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.Text), nullable=True),
        # ── ingestion state ───────────────────────────────────────────────────
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "done",
                "failed",
                "metadata_only",
                name="paperstatus",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=True),
        sa.Column("celery_task_id", sa.Text, nullable=True),
        # ── timestamps ────────────────────────────────────────────────────────
        sa.Column(
            "date_added",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("date_processed", sa.DateTime(timezone=True), nullable=True),
        # ── flexible bag ──────────────────────────────────────────────────────
        sa.Column("extra_metadata", sa.JSON, nullable=True),
    )

    # Indexes
    op.create_index("ix_papers_doi", "papers", ["doi"])
    op.create_index("ix_papers_arxiv_id", "papers", ["arxiv_id"])
    op.create_index("ix_papers_bibtex_key", "papers", ["bibtex_key"])
    op.create_index("ix_papers_status", "papers", ["status"])


def downgrade() -> None:
    op.drop_index("ix_papers_status", table_name="papers")
    op.drop_index("ix_papers_bibtex_key", table_name="papers")
    op.drop_index("ix_papers_arxiv_id", table_name="papers")
    op.drop_index("ix_papers_doi", table_name="papers")
    op.drop_table("papers")
    sa.Enum(name="paperstatus").drop(op.get_bind(), checkfirst=True)
