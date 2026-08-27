"""Phase 0B Alembic baseline with no product-domain schema.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-27
"""

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Alembic records version state; no Phase 1 table is created."""


def downgrade() -> None:
    """No product schema exists to remove."""
