# Owner: Amer
"""Widget loader and token exchange routes.

POST /widgets/token — see specs/001-widget-token-exchange/contracts/widget-token-endpoint.md.
"""

from __future__ import annotations

import json
from functools import lru_cache

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import ValidationError

from app.domain.widget import WidgetTokenRequest
from app.repositories.widget_repo import get_widget_repository
from app.services.rate_limiter import per_ip_rate_limiter, per_widget_rate_limiter
from app.services.widget_service import TokenRefused, WidgetTokenService

router = APIRouter(prefix="/widgets", tags=["widgets"])


# Singleton service per app process. The RateLimiter Protocol means a Redis-backed
# implementation can swap in later without touching this route.
@lru_cache(maxsize=1)
def _service() -> WidgetTokenService:
    return WidgetTokenService(
        repo=get_widget_repository(),
        per_ip_limiter=per_ip_rate_limiter(),
        per_widget_limiter=per_widget_rate_limiter(),
    )


def get_widget_token_service() -> WidgetTokenService:
    return _service()


# FR-007, FR-008, FR-017: every refusal returns this exact body.
_REFUSAL_BODY_BYTES = b'{"error":"widget_unavailable"}'
_BAD_REQUEST_BODY_BYTES = b'{"error":"bad_request"}'
_COMMON_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Type": "application/json",
}


def _byte_response(status_code: int, body_bytes: bytes) -> Response:
    """Return a Response whose body is the exact bytes passed in.

    Avoids JSON-encoder variability (whitespace, key order) that would break
    the byte-equality guarantee in SC-002.
    """
    return Response(
        status_code=status_code, content=body_bytes, headers=_COMMON_HEADERS
    )


def _refusal_response() -> Response:
    return _byte_response(403, _REFUSAL_BODY_BYTES)


def _bad_request_response() -> Response:
    return _byte_response(400, _BAD_REQUEST_BODY_BYTES)


@router.post("/token")
async def exchange_widget_token(
    request: Request,
    service: WidgetTokenService = Depends(get_widget_token_service),
) -> Response:
    """Exchange widget_id and origin for a signed short-lived token."""
    origin = request.headers.get("Origin")
    if not origin:
        return _bad_request_response()

    try:
        raw = await request.json()
    except json.JSONDecodeError:
        return _bad_request_response()

    try:
        body = WidgetTokenRequest.model_validate(raw)
    except ValidationError:
        return _bad_request_response()

    source_ip = request.client.host if request.client else "0.0.0.0"
    try:
        result = await service.issue_token(
            widget_id=body.widget_id, origin=origin, source_ip=source_ip
        )
    except TokenRefused:
        return _refusal_response()

    # Encode the success body once; success responses don't need byte-equality discipline.
    payload = result.model_dump(mode="json")
    return Response(
        status_code=200,
        content=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=_COMMON_HEADERS,
    )
