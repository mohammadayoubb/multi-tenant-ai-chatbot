"""Admin invite response schemas (010 T067).

The revoke / resend routes already return concrete JSON payloads from
`app/api/routes/admin_invites.py`; these schemas document those response
contracts so the OpenAPI doc and integration tests in
``tests/integration/test_admin_invite_revoke_resend.py`` reference a single
source of truth.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InviteRevokeResponse(BaseModel):
    """Shape returned by ``POST /admin/invites/{token}/revoke``."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    revoked_at: datetime | None = None


class InviteResendResponse(BaseModel):
    """Shape returned by ``POST /admin/invites/{token}/resend``.

    The token field carries the **rotated** invite token; the previous token
    is invalidated server-side. `expires_at` is the new expiry.
    """

    model_config = ConfigDict(extra="forbid")

    token: UUID
    email: str
    role: str
    tenant_id: UUID
    expires_at: datetime
