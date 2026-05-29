"""Audit-log feed response schemas (010 T075).

`AuditLogFeedItem` is the shape returned by the TM-scope
``GET /audit-logs`` route (mounted on `tenants.platform_router`). The route
emits one row per audit-log entry filtered by `actor`, `tenant_id`,
`action`, `date_from`, `date_to` query parameters.

Per Principle V (and the audit-vocabulary contract), `metadata_json` carries
no raw PII, no message content, and no full prompt strings — any free-text
excerpts are pre-redacted at the emitter site and bounded at ≤ 80 chars.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogFeedItem(BaseModel):
    """One row of ``GET /audit-logs`` (TM-scope, admin-JWT)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    actor_id: str | None = None
    actor_role: str
    action: str
    metadata_json: dict[str, Any] = {}
    created_at: datetime | None = None
