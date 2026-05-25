# Owner: Hiba
"""FastAPI dependencies.

This file resolves request-scoped dependencies such as tenant context and DB session.
"""

from fastapi import Header, HTTPException


async def get_tenant_id_from_widget_token(authorization: str | None = Header(default=None)) -> int:
    """Resolve tenant_id from a signed widget token.

    This is a placeholder. The real implementation must verify JWT/HMAC token signature.
    """
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing widget token")
    return 1
