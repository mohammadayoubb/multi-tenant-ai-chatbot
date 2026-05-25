# Owner: Hiba
"""Tenant service.

Business rules for tenant provisioning, suspension, and erasure live here.
"""

from app.domain.tenant import TenantDomain
from app.repositories.tenant_repo import TenantRepository


class TenantService:
    """Tenant business logic."""

    def __init__(self, repo: TenantRepository) -> None:
        self._repo = repo

    async def create_tenant(self, name: str) -> TenantDomain:
        """Create a tenant and return a domain model."""
        tenant = await self._repo.create(name)
        return TenantDomain.model_validate(tenant)
