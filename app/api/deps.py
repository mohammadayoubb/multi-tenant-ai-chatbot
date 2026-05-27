# Owner: Hiba
"""FastAPI dependencies.

This file resolves request-scoped dependencies such as tenant context and DB session.
"""

import os
from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException


async def get_tenant_id_from_widget_token(authorization: str | None = Header(default=None)) -> int:
    """Resolve tenant_id from a signed widget token.

    This is a placeholder. The real implementation must verify JWT/HMAC token signature.
    """
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing widget token")
    return 1


@dataclass(frozen=True)
class TenantAdminContext:
    """Trusted context returned by require_tenant_admin.

    Shape contract: tenant_id is the caller's tenant; actor_id is the admin
    user id (or None until the real session model lands). The role check is
    already enforced by the time this object is constructed.
    """

    tenant_id: UUID
    actor_id: str | None


# TODO(hiba-handoff): replace with Hiba's authenticated role dep when it lands.
# Edit authorized for feature 004; see specs/004-widget-admin-config/plan.md
# Complexity Tracking. Until then, the mock reads dev headers and refuses to
# operate outside CONCIERGE_ENV=dev so it cannot ship to staging/prod.
#
# Returns Optional[TenantAdminContext] (not raise-on-refused) so the calling
# route can produce a byte-identical 403 body for every refusal path (contract
# E1/E3 indistinguishability — same bytes whether the role is missing, the
# tenant id is missing, or the row doesn't exist).
async def require_tenant_admin(
    x_concierge_role: str | None = Header(default=None, alias="X-Concierge-Role"),
    x_concierge_tenant_id: str | None = Header(
        default=None, alias="X-Concierge-Tenant-Id"
    ),
    x_concierge_actor_id: str | None = Header(
        default=None, alias="X-Concierge-Actor-Id"
    ),
) -> TenantAdminContext | None:
    """Mock tenant_admin gate.

    Returns a TenantAdminContext when the request carries valid admin headers.
    Returns None when the headers are missing, wrong, or malformed — the route
    handler converts this to the canonical 403 byte response.

    Raises HTTPException(500) outside CONCIERGE_ENV=dev to prevent accidental
    promotion of header-driven auth.
    """
    if os.getenv("CONCIERGE_ENV", "dev") != "dev":
        raise HTTPException(
            status_code=500,
            detail="role-dep mock disabled in non-dev environments",
        )
    if x_concierge_role != "tenant_admin":
        return None
    if not x_concierge_tenant_id:
        return None
    try:
        tenant_id = UUID(x_concierge_tenant_id)
    except ValueError:
        return None
    return TenantAdminContext(tenant_id=tenant_id, actor_id=x_concierge_actor_id)
