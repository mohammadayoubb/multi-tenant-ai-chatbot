# Owner: Hiba
"""Static checks for Hiba-owned migration safety contracts."""

from importlib import import_module
from types import ModuleType


def test_hiba_platform_migration_defines_rls_for_tenant_owned_tables() -> None:
    """The initial migration must protect every current tenant-owned table."""
    migration = _load_migration()

    assert set(migration.TENANT_OWNED_TABLES) == {
        "audit_logs",
        "tenant_usage",
        "tenant_rate_limits",
        "erasure_jobs",
        "cms_pages",
        "leads",
        "conversations",
    }
    assert migration.TENANT_POLICY_NAME == "tenant_isolation"
    assert "current_setting('app.tenant_id', true)" in migration.TENANT_POLICY_EXPR
    assert "tenant_id" in migration.TENANT_POLICY_EXPR


def _load_migration() -> ModuleType:
    """Import the Alembic revision module by dotted path."""
    return import_module("app.db.migrations.versions.0001_hiba_platform_schema_rls")
