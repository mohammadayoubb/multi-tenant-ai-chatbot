# Owner: Hiba
"""CMS domain models."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CmsPageDomain(BaseModel):
    """Safe CMS page response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    title: str
    body: str
