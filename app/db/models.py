# Owner: Hiba
"""SQLAlchemy ORM models.

Every tenant-owned table must include tenant_id.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Tenant(Base):
    """Business tenant."""

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
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

    cms_pages: Mapped[list[CmsPage]] = relationship(back_populates="tenant")
    leads: Mapped[list[Lead]] = relationship(back_populates="tenant")
    conversations: Mapped[list[Conversation]] = relationship(back_populates="tenant")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="tenant")
    usage_events: Mapped[list[TenantUsage]] = relationship(back_populates="tenant")
    rate_limits: Mapped[list[TenantRateLimit]] = relationship(back_populates="tenant")
    erasure_jobs: Mapped[list[ErasureJob]] = relationship(back_populates="tenant")


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
    body: Mapped[str] = mapped_column(Text, nullable=False)
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

    tenant: Mapped[Tenant] = relationship(back_populates="cms_pages")


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
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    intent: Mapped[str] = mapped_column(String(255), nullable=False)
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
    session_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False)
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

    tenant: Mapped[Tenant] = relationship(back_populates="conversations")


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
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
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
    trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    deleted_counts_json: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
