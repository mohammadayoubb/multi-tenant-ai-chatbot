# Owner: Hiba
"""SQLAlchemy ORM models.

Every tenant-owned table must include tenant_id.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Tenant(Base):
    """Business tenant."""

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="starter", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    cms_pages: Mapped[list[CmsPage]] = relationship(back_populates="tenant")
    leads: Mapped[list[Lead]] = relationship(back_populates="tenant")
    conversations: Mapped[list[Conversation]] = relationship(back_populates="tenant")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="tenant")
    usage_events: Mapped[list[TenantUsage]] = relationship(back_populates="tenant")
    rate_limits: Mapped[list[TenantRateLimit]] = relationship(back_populates="tenant")
    erasure_jobs: Mapped[list[ErasureJob]] = relationship(back_populates="tenant")
    admin_users: Mapped[list[AdminUser]] = relationship(back_populates="tenant")
    admin_invites: Mapped[list[AdminInvite]] = relationship(back_populates="tenant")
    memberships: Mapped[list[TenantMembership]] = relationship(back_populates="tenant")
    widget_configs: Mapped[list[WidgetConfig]] = relationship(back_populates="tenant")
    agent_configs: Mapped[list[TenantAgentConfig]] = relationship(back_populates="tenant")
    settings: Mapped[Optional[TenantSettings]] = relationship(
        back_populates="tenant", uselist=False
    )


class AdminUser(Base):
    """Tenant-admin user account (one tenant per admin).

    Authenticates against POST /admin/login; the issued JWT carries tenant_id +
    role and is verified by `require_tenant_admin`. Email is globally unique;
    password is bcrypt-hashed (see app/infra/password.py).
    """

    __tablename__ = "admin_users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="tenant_admin", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship(back_populates="admin_users")


class AdminInvite(Base):
    """Single-use admin invite token.

    Token is a UUID generated server-side and sent to the invitee out-of-band
    (email, shared link). The invitee redeems it on the /accept-invite page,
    which creates the corresponding admin_user row. `tenant_id` and `role` are
    set by the inviter (whose tenant + role come from THEIR JWT, never from
    the request body) and propagated to the new user — the acceptance form
    never lets the invitee choose either.
    """

    __tablename__ = "admin_invites"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    token: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=False, index=True)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), default="tenant_admin", nullable=False)
    invited_by: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship(back_populates="admin_invites")


class CmsPage(Base):
    """Tenant CMS page used by both public website and RAG."""

    __tablename__ = "cms_pages"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="published", nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_cms_pages_tenant_slug"),)

    tenant: Mapped[Tenant] = relationship(back_populates="cms_pages")
    chunks: Mapped[list[RagChunk]] = relationship(back_populates="page")


class Lead(Base):
    """Captured visitor lead."""

    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    conversation_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id"),
        nullable=True,
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    intent: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="captured", nullable=False
    )
    quality_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4, asdecimal=False), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship(back_populates="leads")
    conversation: Mapped[Optional[Conversation]] = relationship(back_populates="leads")


class Conversation(Base):
    """Visitor conversation scoped to one tenant."""

    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    widget_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    session_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "session_id", name="uq_conversations_tenant_session"
        ),
    )

    tenant: Mapped[Tenant] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(back_populates="conversation")
    leads: Mapped[list[Lead]] = relationship(back_populates="conversation")
    escalation_tickets: Mapped[list[EscalationTicket]] = relationship(
        back_populates="conversation"
    )


class AuditLog(Base):
    """Tenant-scoped audit log for platform actions."""

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    actor_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship(back_populates="audit_logs")


class TenantUsage(Base):
    """Per-tenant cost and usage accounting event."""

    __tablename__ = "tenant_usage"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    feature: Mapped[str] = mapped_column(String(50), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_type: Mapped[str] = mapped_column(String(50), nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 6, asdecimal=False),
        nullable=False,
    )
    trace_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship(back_populates="usage_events")


class TenantRateLimit(Base):
    """Configured per-tenant rate limit for one action."""

    __tablename__ = "tenant_rate_limits"
    __table_args__ = (UniqueConstraint("tenant_id", "action"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    limit_count: Mapped[int] = mapped_column(Integer, nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship(back_populates="rate_limits")


class ErasureJob(Base):
    """Tenant erasure bookkeeping record."""

    __tablename__ = "erasure_jobs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    deleted_counts_json: Mapped[dict[str, int]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship(back_populates="erasure_jobs")


# ---------------------------------------------------------------------------
# Contract §8.1 schema-parity additions (migration 0004).
# These ORM classes mirror the tables added by the schema-parity migration.
# Repositories/services for them are owned by their respective contract owners
# (Nasser/Ayoub/Hiba); the models live here so any module can type-check
# against them without duplicating column definitions.
# ---------------------------------------------------------------------------


class User(Base):
    """Authenticated platform/admin user (contract §8.1)."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    memberships: Mapped[list[TenantMembership]] = relationship(back_populates="user")


class TenantMembership(Base):
    """Maps a user to a tenant + role (contract §8.1)."""

    __tablename__ = "tenant_memberships"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_user"),
        CheckConstraint(
            "role IN ('tenant_manager', 'tenant_admin', 'member')",
            name="ck_tenant_memberships_role",
        ),
    )

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class WidgetConfig(Base):
    """Widget identity, allowed origins, theme, greeting, enabled flag."""

    __tablename__ = "widget_configs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    widget_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), unique=True, nullable=False, index=True
    )
    allowed_origins_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    theme_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    greeting: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="widget_configs")


class TenantAgentConfig(Base):
    """Per-tenant persona, enabled tools, and tenant-editable rails."""

    __tablename__ = "tenant_agent_configs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    persona: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled_tools_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    tenant_rails_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="agent_configs")


class TenantSettings(Base):
    """Per-tenant platform defaults the Tenant Manager can edit."""

    __tablename__ = "tenant_settings"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        unique=True,
    )
    default_invite_ttl_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=604800
    )
    rate_limit_chat_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )
    rate_limit_token_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="settings")


class RagChunk(Base):
    """Tenant-scoped chunk + embedding for RAG (pgvector).

    `embedding` is a pgvector column with a fixed dimension (see the migration
    for EMBEDDING_DIM). SQLAlchemy doesn't ship a pgvector type, so we type
    the attribute as `Any`; downstream code uses raw SQL or the `pgvector`
    library's SQLAlchemy adapter to read/write vectors.
    """

    __tablename__ = "rag_chunks"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    page_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cms_pages.id"),
        index=True,
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any] = mapped_column(Text, nullable=False)  # pgvector at the SQL layer
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "page_id", "chunk_index", name="uq_rag_chunks_tenant_page_idx"
        ),
    )

    page: Mapped[CmsPage] = relationship(back_populates="chunks")


class Message(Base):
    """Redacted conversation message + tool trace."""

    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('visitor', 'assistant', 'tool', 'system')",
            name="ck_messages_role",
        ),
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class EscalationTicket(Base):
    """Human follow-up request created by the `escalate` agent tool."""

    __tablename__ = "escalation_tickets"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id"),
        index=True,
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    assigned_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved', 'erased')",
            name="ck_escalation_tickets_status",
        ),
    )

    conversation: Mapped[Conversation] = relationship(back_populates="escalation_tickets")


class Trace(Base):
    """Redacted observability/trace rows (no raw secrets, prompts, or PII)."""

    __tablename__ = "traces"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    trace_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    component: Mapped[str] = mapped_column(String(100), nullable=False)
    event_name: Mapped[str] = mapped_column(String(100), nullable=False)
    redacted_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
