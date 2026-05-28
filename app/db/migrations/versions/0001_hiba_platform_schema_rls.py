# Owner: Hiba
"""Create Hiba platform schema and tenant RLS policies.

Revision ID: 0001_hiba_platform_schema_rls
Revises:
Create Date: 2026-05-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_hiba_platform_schema_rls"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TENANT_OWNED_TABLES = (
    "audit_logs",
    "tenant_usage",
    "tenant_rate_limits",
    "erasure_jobs",
    "cms_pages",
    "leads",
    "conversations",
)

TENANT_POLICY_NAME = "tenant_isolation"
TENANT_POLICY_EXPR = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    """Create platform tables and enable tenant-scoped RLS."""
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'erasing', 'erased')",
            name="ck_tenants_status",
        ),
        sa.UniqueConstraint("name", name="uq_tenants_name"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("actor_role", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])

    op.create_table(
        "tenant_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature", sa.String(length=50), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("unit_type", sa.String(length=50), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("trace_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("units > 0", name="ck_tenant_usage_units_positive"),
        sa.CheckConstraint(
            "feature IN ('chat', 'embedding', 'classifier', 'rag', 'agent', 'guardrails')",
            name="ck_tenant_usage_feature",
        ),
        sa.CheckConstraint(
            "unit_type IN ('tokens', 'requests', 'seconds')",
            name="ck_tenant_usage_unit_type",
        ),
        sa.CheckConstraint(
            "estimated_cost_usd >= 0",
            name="ck_tenant_usage_estimated_cost_non_negative",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_tenant_usage_tenant_id", "tenant_usage", ["tenant_id"])
    op.create_index(
        "ix_tenant_usage_tenant_feature_created",
        "tenant_usage",
        ["tenant_id", "feature", "created_at"],
    )

    op.create_table(
        "tenant_rate_limits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("limit_count", sa.Integer(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("limit_count > 0", name="ck_tenant_rate_limits_limit_positive"),
        sa.CheckConstraint("window_seconds > 0", name="ck_tenant_rate_limits_window_positive"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("tenant_id", "action", name="uq_tenant_rate_limits_tenant_action"),
    )
    op.create_index("ix_tenant_rate_limits_tenant_id", "tenant_rate_limits", ["tenant_id"])

    op.create_table(
        "erasure_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("deleted_counts_json", postgresql.JSONB(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_erasure_jobs_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_erasure_jobs_tenant_id", "erasure_jobs", ["tenant_id"])

    op.create_table(
        "cms_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_cms_pages_tenant_id", "cms_pages", ["tenant_id"])

    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("contact", sa.String(length=255), nullable=True),
        sa.Column("intent", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_leads_tenant_id", "leads", ["tenant_id"])

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_session_id", "conversations", ["session_id"])

    _enable_tenant_rls()


def downgrade() -> None:
    """Drop tenant RLS policies and platform tables."""
    _disable_tenant_rls()

    op.drop_index("ix_conversations_session_id", table_name="conversations")
    op.drop_index("ix_conversations_tenant_id", table_name="conversations")
    op.drop_table("conversations")

    op.drop_index("ix_leads_tenant_id", table_name="leads")
    op.drop_table("leads")

    op.drop_index("ix_cms_pages_tenant_id", table_name="cms_pages")
    op.drop_table("cms_pages")

    op.drop_index("ix_erasure_jobs_tenant_id", table_name="erasure_jobs")
    op.drop_table("erasure_jobs")

    op.drop_index("ix_tenant_rate_limits_tenant_id", table_name="tenant_rate_limits")
    op.drop_table("tenant_rate_limits")

    op.drop_index("ix_tenant_usage_tenant_feature_created", table_name="tenant_usage")
    op.drop_index("ix_tenant_usage_tenant_id", table_name="tenant_usage")
    op.drop_table("tenant_usage")

    op.drop_index("ix_audit_logs_tenant_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_table("tenants")


def _enable_tenant_rls() -> None:
    """Enable RLS and tenant-isolation policy for tenant-owned tables."""
    for table_name in TENANT_OWNED_TABLES:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {TENANT_POLICY_NAME}
            ON {table_name}
            USING ({TENANT_POLICY_EXPR})
            WITH CHECK ({TENANT_POLICY_EXPR})
            """
        )


def _disable_tenant_rls() -> None:
    """Remove tenant-isolation policies from tenant-owned tables."""
    for table_name in TENANT_OWNED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {TENANT_POLICY_NAME} ON {table_name}")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
