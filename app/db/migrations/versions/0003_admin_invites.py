# Owner: Amer
"""Add admin_invites table and admin_users.full_name / status columns.

Revision ID: 0003_admin_invites
Revises: 0002_admin_users
Create Date: 2026-05-28

`admin_invites` carries one row per outstanding invitation; `token` is a UUID
the inviter shares out-of-band. Acceptance is single-use (used_at), expiring
after the inviter-configured TTL.

`admin_users.full_name` is the display name the invitee enters during
acceptance; `admin_users.status` lets the platform suspend a user without
deleting the row — `require_tenant_admin` will refuse a JWT whose user.status
is anything other than 'active'.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003_admin_invites"
down_revision: str | None = "0002_admin_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TENANT_POLICY_NAME = "tenant_isolation"
TENANT_POLICY_EXPR = (
    "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
)


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("full_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "admin_users",
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="active",
        ),
    )
    op.create_check_constraint(
        "ck_admin_users_status",
        "admin_users",
        "status IN ('active', 'suspended')",
    )

    op.create_table(
        "admin_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("invited_by", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
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
        sa.CheckConstraint(
            "role IN ('tenant_admin', 'tenant_manager')",
            name="ck_admin_invites_role",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("token", name="uq_admin_invites_token"),
    )
    op.create_index("ix_admin_invites_tenant_id", "admin_invites", ["tenant_id"])
    op.create_index("ix_admin_invites_token", "admin_invites", ["token"])
    op.create_index("ix_admin_invites_email", "admin_invites", ["email"])

    # Public GET /admin/invites/{token} runs without tenant context (the
    # accepting visitor has no JWT yet), so the lookup uses a bypass session.
    # Tenant-scoped reads from request-scoped sessions still cannot cross
    # tenants thanks to the policy below.
    op.execute("ALTER TABLE admin_invites ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE admin_invites FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {TENANT_POLICY_NAME}
        ON admin_invites
        USING ({TENANT_POLICY_EXPR})
        WITH CHECK ({TENANT_POLICY_EXPR})
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {TENANT_POLICY_NAME} ON admin_invites")
    op.execute("ALTER TABLE admin_invites DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_admin_invites_email", table_name="admin_invites")
    op.drop_index("ix_admin_invites_token", table_name="admin_invites")
    op.drop_index("ix_admin_invites_tenant_id", table_name="admin_invites")
    op.drop_table("admin_invites")

    op.drop_constraint("ck_admin_users_status", "admin_users", type_="check")
    op.drop_column("admin_users", "status")
    op.drop_column("admin_users", "full_name")
