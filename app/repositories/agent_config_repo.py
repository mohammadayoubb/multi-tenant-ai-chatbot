# Owner: Nasser
"""Tenant agent-config repository.

Thin wrapper over the existing TenantAgentConfig ORM model. The repository
returns either the live row or None — the service layer is responsible for
materializing defaults when the row is missing.

All queries are tenant-scoped; tenant_id MUST come from a verified JWT (the
route layer is responsible for that — this repo trusts its caller).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TenantAgentConfig


class TenantAgentConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_tenant(self, tenant_id: UUID) -> TenantAgentConfig | None:
        result = await self._session.execute(
            select(TenantAgentConfig).where(
                TenantAgentConfig.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        tenant_id: UUID,
        *,
        persona: str,
        tenant_rails: dict[str, Any],
    ) -> TenantAgentConfig:
        row = await self.get_by_tenant(tenant_id)
        if row is None:
            row = TenantAgentConfig(
                tenant_id=tenant_id,
                persona=persona,
                enabled_tools_json=["rag_search", "capture_lead", "escalate"],
                tenant_rails_json=tenant_rails,
            )
            self._session.add(row)
        else:
            row.persona = persona
            row.tenant_rails_json = tenant_rails
        await self._session.flush()
        return row
