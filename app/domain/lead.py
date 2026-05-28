# Owner: Nasser
"""Lead domain models."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LeadDomain(BaseModel):
    """Safe lead response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str | None
    contact: str | None
    intent: str
