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


# ---------------------------------------------------------------------------
# T045 — Four canonical visitor flows (FAQ, lead, escalate, refusal)
# ---------------------------------------------------------------------------


def _issue_token(client: TestClient) -> tuple[str, str]:
    """Walk the token-exchange step and return (token, session_id)."""
    resp = client.post(
        "/widgets/token",
        headers={"Origin": FIXTURE_ALLOWED_ORIGIN},
        json={"widget_id": FIXTURE_WIDGET_ID},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["token"], body["session_id"]


def _send_chat(client: TestClient, token: str, session_id: str, message: str):
    return client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": message, "session_id": session_id},
    )


def test_canonical_flow_faq_returns_answer_and_optional_citations(
    client: TestClient,
) -> None:
    """Canonical flow 1 — FAQ. The visitor asks a factual question; the
    chat path returns an `answer` + `route` and optional citations."""
    token, session_id = _issue_token(client)
    resp = _send_chat(client, token, session_id, "What are your business hours?")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body["answer"], str) and body["answer"]
    assert isinstance(body["route"], str)
    # Optional fields: when present, citations must be a list. The widget's
    # defensive parser tolerates absence (api.ts parseChatResponse).
    assert body.get("citations", []) == [] or isinstance(body["citations"], list)


def test_canonical_flow_lead_capture_returns_well_formed_reply(
    client: TestClient,
) -> None:
    """Canonical flow 2 — Lead. A visitor offering contact info gets a
    well-formed reply that includes any tools used (`capture_lead` when
    available; in-memory fallback may route to `agent`)."""
    token, session_id = _issue_token(client)
    resp = _send_chat(
        client,
        token,
        session_id,
        "Please contact me at lead@example.com about a quote",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body["answer"], str)
    assert isinstance(body["used_tools"], list)


def test_canonical_flow_escalate_returns_well_formed_reply(
    client: TestClient,
) -> None:
    """Canonical flow 3 — Escalation. Asking for a human gets a well-formed
    reply; downstream rendering layers handle the ticket_id pill."""
    token, session_id = _issue_token(client)
    resp = _send_chat(client, token, session_id, "I want to talk to a human please")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body["answer"], str)
    # Optional ticket_id: when present, it's either a non-empty string or
    # null. The widget treats both as "no pill" / "pill" respectively.
    if "ticket_id" in body:
        assert body["ticket_id"] is None or isinstance(body["ticket_id"], str)


def test_canonical_flow_refusal_collapses_to_single_widget_unavailable_body(
    client: TestClient,
) -> None:
    """Canonical flow 4 — Cross-tenant / unknown probe. The widget token
    exchange refuses with the byte-identical anti-enumeration body before
    the visitor ever reaches /chat."""
    resp = client.post(
        "/widgets/token",
        headers={"Origin": FIXTURE_ALLOWED_ORIGIN},
        json={"widget_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 403
    assert resp.content == b'{"error":"widget_unavailable"}'
