# Owner: Hiba
"""CMS domain models."""

from pydantic import BaseModel, ConfigDict


class CmsPageDomain(BaseModel):
    """Safe CMS page response model."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    title: str
    body: str
