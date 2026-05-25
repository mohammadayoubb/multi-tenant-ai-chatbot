# Owner: Amer
"""Widget loader and token exchange routes."""

from fastapi import APIRouter

router = APIRouter(prefix="/widgets", tags=["widgets"])


@router.post("/token")
async def exchange_widget_token() -> dict[str, str]:
    """Exchange widget_id and origin for a signed short-lived token."""
    return {"token": "placeholder-token"}
