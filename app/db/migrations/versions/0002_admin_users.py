# Owner: Amer
"""Add admin_users table for tenant-admin authentication.

Revision ID: 0002_admin_users
Revises: 0001_hiba_platform_schema_rls
Create Date: 2026-05-28

One row per admin user. Email is globally unique (login key). Password is
bcrypt-hashed (see app/infra/password.py). Each admin belongs to exactly one
tenant via tenant_id FK; the tenant_id flows into the issued JWT and is the
sole source of tenant identity for downstream admin operations.

RLS is enabled with the same `tenant_isolation` policy expression as the rest
of the platform — admin users cannot read other tenants' admin rows.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_admin_users"
down_revision: str | None = "0001_hiba_platform_schema_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TENANT_POLICY_NAME = "tenant_isolation"
TENANT_POLICY_EXPR = (
    "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
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
            name="ck_admin_users_role",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("email", name="uq_admin_users_email"),
    )
    op.create_index("ix_admin_users_tenant_id", "admin_users", ["tenant_id"])
    op.create_index("ix_admin_users_email", "admin_users", ["email"])

    op.execute("ALTER TABLE admin_users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE admin_users FORCE ROW LEVEL SECURITY")
    # Login lookups happen BEFORE tenant context is set, so the login service
    # must use a tenant-bypass session. The policy exists so any tenant-scoped
    # read from request-scoped sessions still cannot cross tenants.
    op.execute(
        f"""
        CREATE POLICY {TENANT_POLICY_NAME}
        ON admin_users
        USING ({TENANT_POLICY_EXPR})
        WITH CHECK ({TENANT_POLICY_EXPR})
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {TENANT_POLICY_NAME} ON admin_users")
    op.execute("ALTER TABLE admin_users DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_admin_users_email", table_name="admin_users")
    op.drop_index("ix_admin_users_tenant_id", table_name="admin_users")
    op.drop_table("admin_users")
