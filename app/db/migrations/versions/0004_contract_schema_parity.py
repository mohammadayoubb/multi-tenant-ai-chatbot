# Owner: Amer
"""Schema parity with CONTRACT.md §8.1.

Revision ID: 0004_contract_schema_parity
Revises: 0003_admin_invites
Create Date: 2026-05-28

Closes the gap between the live schema (migrations 0001-0003) and the
contract's "Database Structure Contract":

Adds 8 new tables:
    users
    tenant_memberships
    widget_configs
    tenant_agent_configs
    rag_chunks            (pgvector embedding)
    messages
    escalation_tickets
    traces

Alters 4 existing tables:
    tenants               + slug, plan
    cms_pages             + slug, source_url, status, created_by
    conversations         + widget_id, started_at, last_message_at,
                            UNIQUE (tenant_id, session_id)
    leads                 + conversation_id, status, quality_score

All new tenant-owned tables enable RLS with the standard `tenant_isolation`
policy expression so they cannot be queried cross-tenant via a leaked or
missing tenant context.

This migration is intentionally ADDITIVE — it does not drop or rename the
existing `admin_users` / `admin_invites` tables (those still back the login
flow). Migrating admin auth onto `users` + `tenant_memberships` is a separate
follow-up so the live login surface keeps working through this upgrade.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004_contract_schema_parity"
down_revision: str | None = "0003_admin_invites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tables that need the `tenant_isolation` RLS policy added by this migration.
# Existing tenant-owned tables (audit_logs, tenant_usage, etc.) already have
# the policy from 0001; admin_users + admin_invites have it from 0002/0003.
NEW_TENANT_OWNED_TABLES: tuple[str, ...] = (
    "tenant_memberships",
    "widget_configs",
    "tenant_agent_configs",
    "rag_chunks",
    "messages",
    "escalation_tickets",
    "traces",
)

TENANT_POLICY_NAME = "tenant_isolation"
TENANT_POLICY_EXPR = (
    "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
)

# pgvector embedding dimension. 1536 matches OpenAI text-embedding-3-small.
# Adjust here if the project's embedding model changes — pgvector requires a
# fixed dimension per column.
EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    _alter_tenants()
    _create_users()
    _create_tenant_memberships()
    _create_widget_configs()
    _create_tenant_agent_configs()
    _alter_cms_pages()
    _create_rag_chunks()
    _alter_conversations()
    _create_messages()
    _alter_leads()
    _create_escalation_tickets()
    _create_traces()

    _enable_tenant_rls()


def downgrade() -> None:
    _disable_tenant_rls()

    op.drop_index("ix_traces_tenant_id", table_name="traces")
    op.drop_index("ix_traces_trace_id", table_name="traces")
    op.drop_table("traces")

    op.drop_index("ix_escalation_tickets_tenant_id", table_name="escalation_tickets")
    op.drop_index(
        "ix_escalation_tickets_conversation_id", table_name="escalation_tickets"
    )
    op.drop_table("escalation_tickets")

    op.drop_constraint("ck_leads_status", "leads", type_="check")
    op.drop_column("leads", "quality_score")
    op.drop_column("leads", "status")
    op.drop_column("leads", "conversation_id")

    op.drop_index("ix_messages_tenant_id", table_name="messages")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")

    op.drop_constraint(
        "uq_conversations_tenant_session", "conversations", type_="unique"
    )
    op.drop_column("conversations", "last_message_at")
    op.drop_column("conversations", "started_at")
    op.drop_column("conversations", "widget_id")

    op.drop_index("ix_rag_chunks_tenant_id", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_page_id", table_name="rag_chunks")
    op.drop_table("rag_chunks")

    op.drop_constraint("ck_cms_pages_status", "cms_pages", type_="check")
    op.drop_constraint("uq_cms_pages_tenant_slug", "cms_pages", type_="unique")
    op.drop_column("cms_pages", "created_by")
    op.drop_column("cms_pages", "status")
    op.drop_column("cms_pages", "source_url")
    op.drop_column("cms_pages", "slug")

    op.drop_index("ix_tenant_agent_configs_tenant_id", table_name="tenant_agent_configs")
    op.drop_table("tenant_agent_configs")

    op.drop_index("ix_widget_configs_widget_id", table_name="widget_configs")
    op.drop_index("ix_widget_configs_tenant_id", table_name="widget_configs")
    op.drop_table("widget_configs")

    op.drop_constraint(
        "uq_tenant_memberships_tenant_user", "tenant_memberships", type_="unique"
    )
    op.drop_constraint(
        "ck_tenant_memberships_role", "tenant_memberships", type_="check"
    )
    op.drop_index("ix_tenant_memberships_user_id", table_name="tenant_memberships")
    op.drop_index("ix_tenant_memberships_tenant_id", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_constraint("uq_tenants_slug", "tenants", type_="unique")
    op.drop_column("tenants", "plan")
    op.drop_column("tenants", "slug")

    op.execute("DROP EXTENSION IF EXISTS vector")


# ---------------------------------------------------------------------------
# tenants — add slug, plan
# ---------------------------------------------------------------------------


def _alter_tenants() -> None:
    op.add_column("tenants", sa.Column("slug", sa.String(length=255), nullable=True))
    op.add_column("tenants", sa.Column("plan", sa.String(length=50), nullable=True))
    # Backfill: slug from name (deterministic; humans can edit later).
    op.execute(
        "UPDATE tenants SET slug = LOWER(REGEXP_REPLACE(name, '[^a-zA-Z0-9]+', '-', 'g')) "
        "WHERE slug IS NULL"
    )
    op.execute("UPDATE tenants SET plan = 'starter' WHERE plan IS NULL")
    op.alter_column("tenants", "slug", nullable=False)
    op.alter_column("tenants", "plan", nullable=False)
    op.create_unique_constraint("uq_tenants_slug", "tenants", ["slug"])


# ---------------------------------------------------------------------------
# users + tenant_memberships
# ---------------------------------------------------------------------------


def _create_users() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])


def _create_tenant_memberships() -> None:
    op.create_table(
        "tenant_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('tenant_manager', 'tenant_admin', 'member')",
            name="ck_tenant_memberships_role",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "tenant_id", "user_id", name="uq_tenant_memberships_tenant_user"
        ),
    )
    op.create_index(
        "ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"]
    )
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])


# ---------------------------------------------------------------------------
# widget_configs
# ---------------------------------------------------------------------------


def _create_widget_configs() -> None:
    op.create_table(
        "widget_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("widget_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allowed_origins_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "theme_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("greeting", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("widget_id", name="uq_widget_configs_widget_id"),
    )
    op.create_index("ix_widget_configs_tenant_id", "widget_configs", ["tenant_id"])
    op.create_index("ix_widget_configs_widget_id", "widget_configs", ["widget_id"])


# ---------------------------------------------------------------------------
# tenant_agent_configs
# ---------------------------------------------------------------------------


def _create_tenant_agent_configs() -> None:
    op.create_table(
        "tenant_agent_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("persona", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "enabled_tools_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(
                "'[\"rag_search\", \"capture_lead\", \"escalate\"]'::jsonb"
            ),
        ),
        sa.Column(
            "tenant_rails_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index(
        "ix_tenant_agent_configs_tenant_id", "tenant_agent_configs", ["tenant_id"]
    )


# ---------------------------------------------------------------------------
# cms_pages — add slug, source_url, status, created_by
# ---------------------------------------------------------------------------


def _alter_cms_pages() -> None:
    op.add_column("cms_pages", sa.Column("slug", sa.String(length=255), nullable=True))
    op.add_column("cms_pages", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column(
        "cms_pages",
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="published",
        ),
    )
    op.add_column(
        "cms_pages", sa.Column("created_by", sa.String(length=255), nullable=True)
    )
    # Backfill slug from title; this is a one-time deterministic seed.
    op.execute(
        "UPDATE cms_pages SET slug = LOWER(REGEXP_REPLACE(title, '[^a-zA-Z0-9]+', '-', 'g')) "
        "WHERE slug IS NULL"
    )
    op.alter_column("cms_pages", "slug", nullable=False)
    op.create_unique_constraint(
        "uq_cms_pages_tenant_slug", "cms_pages", ["tenant_id", "slug"]
    )
    op.create_check_constraint(
        "ck_cms_pages_status",
        "cms_pages",
        "status IN ('draft', 'published', 'archived')",
    )


# ---------------------------------------------------------------------------
# rag_chunks (pgvector)
# ---------------------------------------------------------------------------


def _create_rag_chunks() -> None:
    op.create_table(
        "rag_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        # Embedding column uses pgvector. The dimension MUST match the model
        # selected at ingest time (see EMBEDDING_DIM). pgvector enforces this.
        sa.Column(
            "embedding",
            sa.dialects.postgresql.ARRAY(sa.Float()),  # placeholder for typing
            nullable=False,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["cms_pages.id"]),
        sa.UniqueConstraint(
            "tenant_id", "page_id", "chunk_index", name="uq_rag_chunks_tenant_page_idx"
        ),
    )
    # Replace the placeholder ARRAY column with the real pgvector type. Using
    # raw SQL because alembic's type registry doesn't know about pgvector.
    op.execute(f"ALTER TABLE rag_chunks DROP COLUMN embedding")
    op.execute(
        f"ALTER TABLE rag_chunks ADD COLUMN embedding vector({EMBEDDING_DIM}) NOT NULL"
    )
    op.create_index("ix_rag_chunks_tenant_id", "rag_chunks", ["tenant_id"])
    op.create_index("ix_rag_chunks_page_id", "rag_chunks", ["page_id"])


# ---------------------------------------------------------------------------
# conversations — add widget_id FK + started_at + last_message_at + UNIQUE
# ---------------------------------------------------------------------------


def _alter_conversations() -> None:
    op.add_column(
        "conversations",
        sa.Column("widget_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "conversations", sa.Column("last_message_at", sa.DateTime(), nullable=True)
    )
    op.create_foreign_key(
        "fk_conversations_widget_id",
        "conversations",
        "widget_configs",
        ["widget_id"],
        ["widget_id"],
    )
    op.create_unique_constraint(
        "uq_conversations_tenant_session",
        "conversations",
        ["tenant_id", "session_id"],
    )


# ---------------------------------------------------------------------------
# messages
# ---------------------------------------------------------------------------


def _create_messages() -> None:
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content_redacted", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('visitor', 'assistant', 'tool', 'system')",
            name="ck_messages_role",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
    )
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])


# ---------------------------------------------------------------------------
# leads — add conversation_id + status + quality_score
# ---------------------------------------------------------------------------


def _alter_leads() -> None:
    op.add_column(
        "leads",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="captured",
        ),
    )
    op.add_column("leads", sa.Column("quality_score", sa.Numeric(5, 4), nullable=True))
    op.create_check_constraint(
        "ck_leads_status",
        "leads",
        "status IN ('captured', 'qualified', 'spam', 'erased')",
    )
    op.create_foreign_key(
        "fk_leads_conversation_id",
        "leads",
        "conversations",
        ["conversation_id"],
        ["id"],
    )


# ---------------------------------------------------------------------------
# escalation_tickets
# ---------------------------------------------------------------------------


def _create_escalation_tickets() -> None:
    op.create_table(
        "escalation_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="open"),
        sa.Column("assigned_to", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved', 'erased')",
            name="ck_escalation_tickets_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
    )
    op.create_index(
        "ix_escalation_tickets_tenant_id", "escalation_tickets", ["tenant_id"]
    )
    op.create_index(
        "ix_escalation_tickets_conversation_id",
        "escalation_tickets",
        ["conversation_id"],
    )


# ---------------------------------------------------------------------------
# traces
# ---------------------------------------------------------------------------


def _create_traces() -> None:
    op.create_table(
        "traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trace_id", sa.String(length=255), nullable=False),
        sa.Column("component", sa.String(length=100), nullable=False),
        sa.Column("event_name", sa.String(length=100), nullable=False),
        sa.Column(
            "redacted_payload_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_traces_tenant_id", "traces", ["tenant_id"])
    op.create_index("ix_traces_trace_id", "traces", ["trace_id"])


# ---------------------------------------------------------------------------
# RLS — enable + tenant_isolation policy on each new tenant-owned table
# ---------------------------------------------------------------------------


def _enable_tenant_rls() -> None:
    for table_name in NEW_TENANT_OWNED_TABLES:
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
    for table_name in NEW_TENANT_OWNED_TABLES:
        op.execute(
            f"DROP POLICY IF EXISTS {TENANT_POLICY_NAME} ON {table_name}"
        )
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
