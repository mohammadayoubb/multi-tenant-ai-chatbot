# Owner: Hiba
"""Static checks for Hiba-owned migration safety contracts."""

from configparser import ConfigParser
from importlib import import_module
from pathlib import Path
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


def test_alembic_runtime_is_wired_to_hiba_migrations() -> None:
    """Alembic should discover Hiba's migration package from the repo root."""
    parser = ConfigParser()
    parser.read("alembic.ini")

    assert parser["alembic"]["script_location"] == "app/db/migrations"
    assert parser["alembic"]["prepend_sys_path"] == "."
    assert "placeholder" in parser["alembic"]["sqlalchemy.url"]


def test_alembic_env_uses_vault_resolved_sync_database_url() -> None:
    """The runtime env must resolve DB credentials from Vault, not alembic.ini."""
    env_source = Path("app/db/migrations/env.py").read_text()

    assert "get_app_secrets" in env_source
    assert "sync_database_url" in env_source
    assert "Base.metadata" in env_source


def test_alembic_revision_template_keeps_hiba_owner_header() -> None:
    """New generated migration files should keep ownership explicit."""
    template_source = Path("app/db/migrations/script.py.mako").read_text()

    assert template_source.startswith("# Owner: Hiba")


def _load_migration() -> ModuleType:
    """Import the Alembic revision module by dotted path."""
    return import_module("app.db.migrations.versions.0001_hiba_platform_schema_rls")
