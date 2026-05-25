# Owner: Nasser
"""Unit tests for classifier-driven router."""

import pytest

from app.agent.router import route_message


@pytest.mark.asyncio
async def test_router_escalates_human_request() -> None:
    """Router should escalate explicit human requests."""
    result = await route_message("I want to talk to a human")
    assert result == "escalate"
