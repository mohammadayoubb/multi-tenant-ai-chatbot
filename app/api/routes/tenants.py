# Owner: Hiba
"""Tenant management routes."""

from fastapi import APIRouter

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("")
async def create_tenant() -> dict[str, str]:
    """Placeholder tenant provisioning endpoint."""
    return {"status": "tenant creation placeholder"}
