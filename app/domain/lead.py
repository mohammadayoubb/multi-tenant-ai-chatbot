# Owner: Nasser
"""Lead domain models."""

from pydantic import BaseModel, ConfigDict


class LeadDomain(BaseModel):
    """Safe lead response model."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    name: str | None
    contact: str | None
    intent: str
