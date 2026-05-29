# Owner: Hiba
"""Schema for the admin-users list endpoint (T031).

Shape returned by ``GET /tenants/{tid}/admin-users`` — used to populate the
assignee dropdown on the Escalations tab. Only same-tenant rows are returned;
the route layer enforces ``tid == jwt.tenant_id`` (byte-uniform 403 otherwise).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AdminUserListItem(BaseModel):
    """One row of ``GET /tenants/{tid}/admin-users``."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    full_name: str | None = None
    email: str
    role: str
    status: str
