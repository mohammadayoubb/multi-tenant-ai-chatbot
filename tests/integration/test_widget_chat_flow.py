# Owner: Amer
"""End-to-end widget integration: token exchange + chat in one flow.

This exercises the full wiring the embedded widget actually uses:
  1. POST /widgets/token  -> HS256 JWT bound to (tenant_id, widget_id, origin)
  2. POST /chat           -> get_tenant_id_from_widget_token verifies the JWT
                              and ChatService runs the visitor turn

Replaces the prior `test_chat_placeholder.py` no-op now that the
`get_tenant_id_from_widget_token` handoff (BLOCKED.md H1) has landed.

`get_session` is overridden to yield None so the test does not require a
running Postgres. The chat path's helpers (`retrieve_chunks`, `capture_lead`)
are session-aware and return safe in-memory fallbacks when session is None,
which is enough to assert the wiring.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import app
from app.repositories.widget_repo import InMemoryWidgetRepository

# In-memory widget fixture: see InMemoryWidgetRepository constructor.
FIXTURE_WIDGET_ID = str(InMemoryWidgetRepository._FIXTURE_WIDGET_ID)
FIXTURE_TENANT_ID = str(InMemoryWidgetRepository._FIXTURE_TENANT_ID)
FIXTURE_ALLOWED_ORIGIN = "http://localhost:5173"


async def _no_db_session() -> AsyncGenerator[None, None]:
    """get_session override that yields None — the chat path tolerates it."""
    yield None


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_session] = _no_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_full_widget_to_chat_flow_succeeds(client: TestClient) -> None:
    """Token from /widgets/token must authenticate a subsequent /chat call."""
    token_resp = client.post(
        "/widgets/token",
        headers={"Origin": FIXTURE_ALLOWED_ORIGIN},
        json={"widget_id": FIXTURE_WIDGET_ID},
    )
    assert token_resp.status_code == 200, token_resp.text
    token_body = token_resp.json()
    assert isinstance(token_body["token"], str) and token_body["token"]
    assert token_body["expires_in"] > 0
    assert isinstance(token_body["session_id"], str)

    chat_resp = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token_body['token']}"},
        json={
            "message": "What are your business hours?",
            "session_id": token_body["session_id"],
        },
    )
    assert chat_resp.status_code == 200, chat_resp.text
    body = chat_resp.json()
    # ChatResponse contract: answer + route + used_tools.
    assert isinstance(body["answer"], str) and body["answer"]
    assert isinstance(body["route"], str) and body["route"]
    assert isinstance(body["used_tools"], list)


def test_chat_without_bearer_is_401(client: TestClient) -> None:
    """No Authorization header -> 401 (collapses with all other bad-token paths)."""
    resp = client.post(
        "/chat",
        json={"message": "hi", "session_id": "s-1"},
    )
    assert resp.status_code == 401


def test_chat_with_bogus_bearer_is_401(client: TestClient) -> None:
    """Unsigned / unparseable token -> same 401."""
    resp = client.post(
        "/chat",
        headers={"Authorization": "Bearer not-a-real-jwt"},
        json={"message": "hi", "session_id": "s-1"},
    )
    assert resp.status_code == 401


def test_chat_with_token_from_disallowed_origin_never_issues(
    client: TestClient,
) -> None:
    """An origin not on the widget's allowlist gets a refused-byte 403 at /widgets/token,
    so there is no token to take to /chat in the first place."""
    resp = client.post(
        "/widgets/token",
        headers={"Origin": "https://attacker.example"},
        json={"widget_id": FIXTURE_WIDGET_ID},
    )
    assert resp.status_code == 403
    assert resp.content == b'{"error":"widget_unavailable"}'
