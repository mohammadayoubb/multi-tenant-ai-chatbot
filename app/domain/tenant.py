# Owner: Hiba
"""Tenant domain models."""

from pydantic import BaseModel, ConfigDict


class TenantDomain(BaseModel):
    """Safe tenant response model."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
