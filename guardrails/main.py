# Owner: Ayoub
"""Guardrails sidecar.

Platform rails are mandatory and tenant rails cannot weaken them.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Concierge Guardrails")


class GuardrailRequest(BaseModel):
    """Guardrail check request."""

    tenant_id: int
    text: str


class GuardrailResponse(BaseModel):
    """Guardrail check response."""

    allowed: bool
    reason: str | None = None


@app.post("/check", response_model=GuardrailResponse)
async def check(request: GuardrailRequest) -> GuardrailResponse:
    """Check text against platform guardrails."""
    blocked_terms = ["system prompt", "another tenant", "tenant b"]
    if any(term in request.text.lower() for term in blocked_terms):
        return GuardrailResponse(allowed=False, reason="Blocked by platform rail.")
    return GuardrailResponse(allowed=True)
