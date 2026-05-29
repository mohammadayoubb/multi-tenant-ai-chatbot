"""Add tenant_settings table for TM-scope writable platform defaults.

Revision ID: 0006_tenant_settings
Revises: 0005_admin_invites_revoked_at
Create Date: 2026-05-29

Schema:
    tenant_settings (
      id                              uuid pk,
      tenant_id                       uuid NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
      default_invite_ttl_seconds      int NOT NULL DEFAULT 604800,
      rate_limit_chat_per_minute      int NOT NULL DEFAULT 30,
      rate_limit_token_per_minute     int NOT NULL DEFAULT 60,
      rate_limit_lead_per_session     int NOT NULL DEFAULT 5,
      created_at / updated_at         timestamps
    )

`rate_limit_lead_per_session` (feature 010 §R7) backs the Track-2
`capture_lead` per-session bucket. Bundled into 0006 rather than a separate
0007 migration because 0006 has not shipped yet (Principle VII).

UNIQUE(tenant_id) guarantees at most one settings row per tenant; the service
layer treats first read as upsert-of-defaults.

RLS: standard `tenant_isolation` policy mirrored from the other tenant tables.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006_tenant_settings"
down_revision: str | None = "0005_admin_invites_revoked_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TENANT_POLICY_NAME = "tenant_isolation"
TENANT_POLICY_EXPR = (
    "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "tenant_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "default_invite_ttl_seconds",
            sa.Integer(),
            nullable=False,
            server_default="604800",
        ),
        sa.Column(
            "rate_limit_chat_per_minute",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
        sa.Column(
            "rate_limit_token_per_minute",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
        sa.Column(
            "rate_limit_lead_per_session",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_settings_tenant_id"),
    )
    op.create_index(
        "ix_tenant_settings_tenant_id", "tenant_settings", ["tenant_id"]
    )

    op.execute("ALTER TABLE tenant_settings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_settings FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {TENANT_POLICY_NAME}
        ON tenant_settings
        USING ({TENANT_POLICY_EXPR})
        WITH CHECK ({TENANT_POLICY_EXPR})
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {TENANT_POLICY_NAME} ON tenant_settings")
    op.execute("ALTER TABLE tenant_settings DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_tenant_settings_tenant_id", table_name="tenant_settings")
    op.drop_table("tenant_settings")
