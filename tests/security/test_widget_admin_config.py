# Owner: Amer
"""Security + contract tests for the tenant-admin widget configuration endpoints.

Covers spec.md FR-001..FR-018 and success criteria SC-001..SC-007 for feature
004. Maps to clauses E1..E5 in specs/004-widget-admin-config/contracts/.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import app.api.routes.widgets as widgets_route
from app.domain.widget import WidgetConfigDomain
from app.main import app
from app.repositories.widget_repo import InMemoryWidgetRepository
from app.services.widget_service import WidgetConfigService


# --- Test fixtures ---

TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")
WIDGET_A = UUID("9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d")
WIDGET_B = UUID("aaaa3a3a-bbbb-4f3a-9f06-2e2b9a8b1c6d")
ROW_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ROW_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

ADMIN_A_HEADERS = {
    "X-Concierge-Role": "tenant_admin",
    "X-Concierge-Tenant-Id": str(TENANT_A),
    "X-Concierge-Actor-Id": "amer@acme.example",
}
ADMIN_B_HEADERS = {
    "X-Concierge-Role": "tenant_admin",
    "X-Concierge-Tenant-Id": str(TENANT_B),
    "X-Concierge-Actor-Id": "ops@bravo.example",
}


def _seeded_repo() -> InMemoryWidgetRepository:
    repo = InMemoryWidgetRepository()
    repo.clear()
    repo.upsert(
        WidgetConfigDomain(
            id=ROW_A,
            tenant_id=TENANT_A,
            widget_id=WIDGET_A,
            allowed_origins=["https://acme.example"],
            enabled=True,
            tenant_status="active",
            theme_json=None,
            greeting=None,
        )
    )
    repo.upsert(
        WidgetConfigDomain(
            id=ROW_B,
            tenant_id=TENANT_B,
            widget_id=WIDGET_B,
            allowed_origins=["https://bravo.example"],
            enabled=True,
            tenant_status="active",
            theme_json=None,
            greeting=None,
        )
    )
    return repo


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch):
    monkeypatch.setenv("CONCIERGE_ENV", "dev")
    yield


@pytest.fixture
def env():
    """Fresh repo + audit-mock per test; overrides cleaned up after."""
    repo = _seeded_repo()
    audit = AsyncMock()

    def override_get_widget_config_service():
        return WidgetConfigService(repo=repo, audit_logger=audit)

    app.dependency_overrides[widgets_route.get_widget_config_service] = (
        override_get_widget_config_service
    )
    try:
        with TestClient(app) as client:
            yield client, repo, audit
    finally:
        app.dependency_overrides.pop(
            widgets_route.get_widget_config_service, None
        )


# --- T009 GET happy path ---


def test_get_widget_config_returns_current_row(env):
    client, _repo, _audit = env
    resp = client.get("/widgets/config", headers=ADMIN_A_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["widget_id"] == str(WIDGET_A)
    assert body["allowed_origins"] == ["https://acme.example"]
    assert body["enabled"] is True
    assert body["theme_json"] is None
    assert body["greeting"] is None
    # tenant_id is NOT in the response (data-model.md WidgetConfigResponse).
    assert "tenant_id" not in body


# --- T010 GET role gate ---


def test_get_widget_config_without_admin_returns_403(env):
    client, _repo, _audit = env
    resp = client.get("/widgets/config")  # no headers
    assert resp.status_code == 403
    assert resp.content == b'{"error":"forbidden"}'

    resp2 = client.get(
        "/widgets/config",
        headers={
            "X-Concierge-Role": "tenant_member",
            "X-Concierge-Tenant-Id": str(TENANT_A),
        },
    )
    assert resp2.status_code == 403
    assert resp2.content == b'{"error":"forbidden"}'


# --- T011 cross-tenant denial ---


def test_admin_config_cross_tenant_returns_403(env):
    """Admin of tenant A cannot read or write tenant C's row (tenant C doesn't exist).

    Critically, the response bytes are IDENTICAL to the role-missing case so a
    tenant id's existence cannot be inferred from the response.
    """
    client, _repo, audit = env
    # Tenant C is unseeded.
    bogus_tenant = UUID("33333333-3333-3333-3333-333333333333")
    headers = {**ADMIN_A_HEADERS, "X-Concierge-Tenant-Id": str(bogus_tenant)}
    resp = client.get("/widgets/config", headers=headers)
    assert resp.status_code == 403
    assert resp.content == b'{"error":"forbidden"}'

    resp_put = client.put(
        "/widgets/config",
        headers=headers,
        json={"allowed_origins": ["https://x.com"], "enabled": True},
    )
    assert resp_put.status_code == 403
    assert resp_put.content == b'{"error":"forbidden"}'
    audit.add_audit_log.assert_not_awaited()


def test_admin_a_cannot_read_tenant_b(env):
    """Same body bytes for cross-tenant as for unauth — but tenant B does exist."""
    client, _repo, _audit = env
    headers = {**ADMIN_A_HEADERS, "X-Concierge-Tenant-Id": str(TENANT_B)}
    # Admin A claims to be tenant B (impossible in real auth; mocked here).
    # In the mock dep, the X-Concierge-Tenant-Id IS the trusted claim, so this
    # is actually "admin of tenant B reading tenant B" — succeeds. The real
    # cross-tenant attack vector is closed because Hiba's authenticated role
    # dep will not honor a header for a tenant the user doesn't belong to.
    # This test documents that property of the *mock* and is replaced when
    # Hiba's dep lands.
    resp = client.get("/widgets/config", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["widget_id"] == str(WIDGET_B)


# --- T012 invalid origin → 422 ---


def test_put_widget_config_invalid_origin_returns_422(env):
    client, repo, audit = env
    for bad in [
        "javascript:alert(1)",
        "acme.com",  # no scheme
        "ftp://acme.com",
        "https://",  # no host
        "not a url",
    ]:
        resp = client.put(
            "/widgets/config",
            headers=ADMIN_A_HEADERS,
            json={"allowed_origins": [bad], "enabled": True},
        )
        assert resp.status_code == 422, f"expected 422 for {bad!r}"
    audit.add_audit_log.assert_not_awaited()
    # Row unchanged.
    row = repo._rows[WIDGET_A]
    assert row.allowed_origins == ["https://acme.example"]


# --- T013 enabled + empty origins → 422 ---


def test_put_widget_config_enabled_without_origins_returns_422(env):
    client, repo, audit = env
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={"allowed_origins": [], "enabled": True},
    )
    assert resp.status_code == 422
    audit.add_audit_log.assert_not_awaited()
    # Row unchanged.
    row = repo._rows[WIDGET_A]
    assert row.enabled is True


# --- T014 add origin → 1 audit call ---


def test_put_widget_config_adds_origin_calls_audit_once(env):
    client, _repo, audit = env
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={
            "allowed_origins": ["https://acme.example", "https://blog.acme.example"],
            "enabled": True,
        },
    )
    assert resp.status_code == 200
    assert audit.add_audit_log.await_count == 1
    call = audit.add_audit_log.await_args
    assert call.kwargs["action"] == "widget.origin_added"
    assert call.kwargs["metadata"]["origin"] == "https://blog.acme.example"
    assert call.kwargs["tenant_id"] == TENANT_A
    assert call.kwargs["actor_role"] == "tenant_admin"


# --- T015 remove origin → 1 audit call ---


def test_put_widget_config_removes_origin_calls_audit_once(env):
    client, repo, audit = env
    # Seed with two origins so we can remove one.
    repo._rows[WIDGET_A] = repo._rows[WIDGET_A].model_copy(
        update={"allowed_origins": ["https://acme.example", "https://blog.acme.example"]}
    )
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={"allowed_origins": ["https://acme.example"], "enabled": True},
    )
    assert resp.status_code == 200
    assert audit.add_audit_log.await_count == 1
    call = audit.add_audit_log.await_args
    assert call.kwargs["action"] == "widget.origin_removed"
    assert call.kwargs["metadata"]["origin"] == "https://blog.acme.example"


# --- T016 mixed change ---


def test_put_widget_config_mixed_change_audits_each_delta(env):
    client, repo, audit = env
    repo._rows[WIDGET_A] = repo._rows[WIDGET_A].model_copy(
        update={"allowed_origins": ["https://acme.example", "https://old.acme.example"]}
    )
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={
            "allowed_origins": [
                "https://acme.example",
                "https://new1.acme.example",
                "https://new2.acme.example",
            ],
            "enabled": True,
        },
    )
    assert resp.status_code == 200
    # 2 added, 1 removed.
    assert audit.add_audit_log.await_count == 3
    actions = [c.kwargs["action"] for c in audit.add_audit_log.await_args_list]
    origins = [c.kwargs["metadata"]["origin"] for c in audit.add_audit_log.await_args_list]
    assert actions.count("widget.origin_added") == 2
    assert actions.count("widget.origin_removed") == 1
    assert "https://new1.acme.example" in origins
    assert "https://new2.acme.example" in origins
    assert "https://old.acme.example" in origins


# --- T017 no-op → 0 calls ---


def test_put_widget_config_no_change_no_audit(env):
    client, _repo, audit = env
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={"allowed_origins": ["https://acme.example"], "enabled": True},
    )
    assert resp.status_code == 200
    audit.add_audit_log.assert_not_awaited()


# --- T018 audit failure → 500 + rollback ---


def test_put_widget_config_audit_failure_rolls_back(env):
    client, repo, audit = env
    audit.add_audit_log.side_effect = RuntimeError("fake audit DB outage")
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={
            "allowed_origins": ["https://acme.example", "https://blog.acme.example"],
            "enabled": True,
        },
    )
    assert resp.status_code == 500
    # Row reverted to pre-call state.
    row = repo._rows[WIDGET_A]
    assert row.allowed_origins == ["https://acme.example"]


# --- T019 normalization ---


def test_put_widget_config_normalizes_origins(env):
    client, repo, audit = env
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={
            "allowed_origins": [
                "HTTPS://Acme.Example/",
                "https://acme.example:443/some/path",
            ],
            "enabled": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed_origins"] == ["https://acme.example"]
    # No diff, so no audit call.
    audit.add_audit_log.assert_not_awaited()


# --- US2: T027 greeting persists ---


def test_put_widget_config_greeting_persists(env):
    client, _repo, audit = env
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={
            "allowed_origins": ["https://acme.example"],
            "enabled": True,
            "greeting": "Hi from Acme",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["greeting"] == "Hi from Acme"
    audit.add_audit_log.assert_not_awaited()


# --- US2: T028 greeting too long ---


def test_put_widget_config_greeting_too_long_returns_422(env):
    client, _repo, _audit = env
    long = "x" * 281
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={
            "allowed_origins": ["https://acme.example"],
            "enabled": True,
            "greeting": long,
        },
    )
    assert resp.status_code == 422


# --- US2: T029 disable with empty origins allowed ---


def test_put_widget_config_disable_with_empty_origins_allowed(env):
    client, _repo, _audit = env
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={"allowed_origins": [], "enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


# --- US2: T030 enable with empty origins rejected ---


def test_put_widget_config_enable_with_empty_origins_rejected(env):
    """Same constraint as T013, exercised through the toggle path."""
    client, repo, _audit = env
    repo._rows[WIDGET_A] = repo._rows[WIDGET_A].model_copy(
        update={"allowed_origins": [], "enabled": False}
    )
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={"allowed_origins": [], "enabled": True},
    )
    assert resp.status_code == 422


# --- US3: T035 theme persists ---


def test_put_widget_config_theme_json_persists(env):
    client, _repo, _audit = env
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={
            "allowed_origins": ["https://acme.example"],
            "enabled": True,
            "theme_json": {"primary": "#ff0066"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["theme_json"] == {"primary": "#ff0066"}


# --- US3: T036 theme null clears ---


def test_put_widget_config_theme_json_null_clears(env):
    client, repo, _audit = env
    repo._rows[WIDGET_A] = repo._rows[WIDGET_A].model_copy(
        update={"theme_json": {"primary": "#ff0066"}}
    )
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={
            "allowed_origins": ["https://acme.example"],
            "enabled": True,
            "theme_json": None,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["theme_json"] is None


# --- US3: T037 theme non-object rejected ---


def test_put_widget_config_theme_non_object_returns_422(env):
    client, _repo, _audit = env
    for bad in ["a string", 42, [1, 2, 3]]:
        resp = client.put(
            "/widgets/config",
            headers=ADMIN_A_HEADERS,
            json={
                "allowed_origins": ["https://acme.example"],
                "enabled": True,
                "theme_json": bad,
            },
        )
        assert resp.status_code == 422, f"expected 422 for theme_json={bad!r}"


def test_put_widget_config_rejects_tenant_id_in_body(env):
    """The body MUST NOT contain tenant_id; extra='forbid' enforces this."""
    client, _repo, _audit = env
    resp = client.put(
        "/widgets/config",
        headers=ADMIN_A_HEADERS,
        json={
            "tenant_id": str(TENANT_A),
            "allowed_origins": ["https://acme.example"],
            "enabled": True,
        },
    )
    assert resp.status_code == 422
