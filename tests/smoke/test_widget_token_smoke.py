# Owner: Amer
"""Smoke test: token endpoint can issue and decode one token end-to-end.

Independent of any other teammate's slice (uses the in-memory widget repo backend).
Wired into CI as a fast safety net for the full Phase 7 e2e in amer-works.md.
"""

from __future__ import annotations

from uuid import UUID

import jwt
from fastapi.testclient import TestClient

from app.main import app
from app.services.widget_settings import widget_settings

WIDGET_ID = UUID("9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d")
ORIGIN = "http://localhost:5500"


def test_widget_token_smoke() -> None:
    client = TestClient(app)
    res = client.post(
        "/widgets/token",
        headers={"Origin": ORIGIN},
        json={"widget_id": str(WIDGET_ID)},
    )
    assert res.status_code == 200, res.text
    claims = jwt.decode(
        res.json()["token"],
        widget_settings().widget_jwt_secret,
        algorithms=["HS256"],
    )
    assert claims["widget_id"] == str(WIDGET_ID)
    assert claims["origin"] == ORIGIN
