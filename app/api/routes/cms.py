# Owner: Hiba
"""CMS routes for tenant admins."""

from fastapi import APIRouter

router = APIRouter(prefix="/cms", tags=["cms"])


@router.get("/pages")
async def list_pages() -> dict[str, list[str]]:
    """Placeholder CMS listing endpoint."""
    return {"pages": []}
