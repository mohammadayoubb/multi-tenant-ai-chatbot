# Owner: Hiba
"""Migration unit tests for feature 010 (task T008).

Static checks over the alembic migration files for 0005 and 0006:

- 0005 ``admin_invites.revoked_at`` is a nullable TIMESTAMP / DateTime add-column.
- 0006 ``tenant_settings`` creates the table with RLS enabled, includes the
  ``rate_limit_lead_per_session`` column added in §R7 (task T007), and pairs
  every ``upgrade`` action with a matching ``downgrade`` action.

A live upgrade-downgrade-upgrade cycle against a seeded copy of the demo DB
is the harder validation called out in tasks.md; the contract for this unit
test is "the migration files match the spec without running them". The
live cycle is run by `pytest tests/integration/test_migrations_cycle.py`
behind the Compose stack — out of scope for the unit suite.
"""

from __future__ import annotations

from pathlib import Path

MIGRATIONS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "db"
    / "migrations"
    / "versions"
)


def _read(name: str) -> str:
    return (MIGRATIONS_DIR / name).read_text(encoding="utf-8")


def test_0005_adds_revoked_at_nullable_column() -> None:
    body = _read("0005_admin_invites_revoked_at.py")
    assert 'op.add_column(\n        "admin_invites",' in body
    assert '"revoked_at"' in body
    assert "nullable=True" in body
    assert 'op.drop_column("admin_invites", "revoked_at")' in body


def test_0005_chains_off_0004() -> None:
    body = _read("0005_admin_invites_revoked_at.py")
    assert 'down_revision: str | None = "0004_contract_schema_parity"' in body
    assert 'revision: str = "0005_admin_invites_revoked_at"' in body


def test_0006_creates_tenant_settings_with_required_columns() -> None:
    body = _read("0006_tenant_settings.py")
    assert 'op.create_table(\n        "tenant_settings"' in body
    for column in (
        '"default_invite_ttl_seconds"',
        '"rate_limit_chat_per_minute"',
        '"rate_limit_token_per_minute"',
        '"rate_limit_lead_per_session"',  # task T007
        '"created_at"',
        '"updated_at"',
    ):
        assert column in body, f"missing column {column} in migration 0006"


def test_0006_rate_limit_lead_per_session_default_is_5() -> None:
    body = _read("0006_tenant_settings.py")
    # The column is server_default="5" per data-model.md.
    assert '"rate_limit_lead_per_session"' in body
    rl_block_start = body.index('"rate_limit_lead_per_session"')
    snippet = body[rl_block_start : rl_block_start + 200]
    assert 'server_default="5"' in snippet


def test_0006_enables_row_level_security() -> None:
    body = _read("0006_tenant_settings.py")
    assert "ALTER TABLE tenant_settings ENABLE ROW LEVEL SECURITY" in body
    assert "ALTER TABLE tenant_settings FORCE ROW LEVEL SECURITY" in body
    assert "CREATE POLICY" in body
    assert "tenant_isolation" in body


def test_0006_downgrade_is_symmetric() -> None:
    body = _read("0006_tenant_settings.py")
    assert "DROP POLICY IF EXISTS" in body
    assert "DISABLE ROW LEVEL SECURITY" in body
    assert 'op.drop_index("ix_tenant_settings_tenant_id"' in body
    assert 'op.drop_table("tenant_settings")' in body


def test_0006_chains_off_0005() -> None:
    body = _read("0006_tenant_settings.py")
    assert 'down_revision: str | None = "0005_admin_invites_revoked_at"' in body
    assert 'revision: str = "0006_tenant_settings"' in body
