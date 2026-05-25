# Owner: Nasser
"""Lead repository.

The capture_lead tool writes through this repository.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lead


class LeadRepository:
    """SQL operations for captured leads."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, tenant_id: int, name: str | None, contact: str | None, intent: str) -> Lead:
        """Create a tenant-scoped lead."""
        lead = Lead(tenant_id=tenant_id, name=name, contact=contact, intent=intent)
        self._session.add(lead)
        await self._session.flush()
        return lead
