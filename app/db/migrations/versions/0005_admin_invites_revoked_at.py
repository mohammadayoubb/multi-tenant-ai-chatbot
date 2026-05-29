"""Add revoked_at to admin_invites so revoke is a first-class lifecycle state.

Revision ID: 0005_admin_invites_revoked_at
Revises: 0004_contract_schema_parity
Create Date: 2026-05-29

`revoked_at` lets an inviter (or tenant manager) take back an outstanding
invitation. The service-layer status function treats a row with `revoked_at`
set the same way it treats a `used_at` row: 409 on accept, 409 on revoke,
409 on resend.

Idempotent: column add is nullable with no backfill (existing rows are
treated as not-revoked).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_admin_invites_revoked_at"
down_revision: str | None = "0004_contract_schema_parity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_invites",
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("admin_invites", "revoked_at")
