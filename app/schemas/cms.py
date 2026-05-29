# Owner: Nasser
"""Schemas for the CMS edit / status / delete endpoints (T034).

The CMS service layer already owns the authoritative validators
(``CmsPageUpdateBody`` and ``CmsPageStatusBody`` in
``app/services/cms_pages.py``). These exported schemas re-state the same
contract for callers that want to import from ``app.schemas`` rather than
the service module, matching the convention established by ``app/schemas/
tenant.py``.

``tenant_id`` / ``actor_id`` / ``role`` are intentionally absent on every body
— they derive from the admin JWT in the route layer (``extra=forbid`` rejects
any smuggled identity field with 422).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CmsPageUpdateRequest(BaseModel):
    """Body for ``PUT /cms/pages/{id}``."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, min_length=1)
    source_url: str | None = None
    status: str | None = Field(
        default=None, pattern="^(draft|published|archived)$"
    )


class CmsPageStatusPatchRequest(BaseModel):
    """Body for ``PATCH /cms/pages/{id}/status``."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(draft|published|archived)$")
