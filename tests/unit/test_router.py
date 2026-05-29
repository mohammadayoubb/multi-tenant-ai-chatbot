# Owner: Nasser
"""Unit tests for the classifier-driven router (T049).

Covers one case per decision branch in app/agent/router.py:
  1. high-confidence faq          -> rag_search (workflow)
  2. spam                          -> blocked
  3. ambiguous                     -> agent
  4. low-confidence non-spam       -> agent (fail-soft)
  5. modelserver error             -> agent (fail-soft, reason=modelserver_unavailable)
"""

from __future__ import annotations

import pytest

from app.agent.router import route_message, route_message_decision
from app.infra.modelserver import (
    ModelserverClient,
    ModelserverClientError,
    ModelserverPrediction,
    RouterLabel,
)


class _StubModelserverClient(ModelserverClient):
    """In-memory stub that returns a canned prediction or raises."""

    def __init__(
        self,
        *,
        label: RouterLabel | None = None,
        confidence: float = 0.0,
        raises: bool = False,
    ) -> None:
        # Intentionally skip super().__init__ — we never hit the network.
        self._label = label
        self._confidence = confidence
        self._raises = raises

    async def predict(self, message: str) -> ModelserverPrediction:  # type: ignore[override]
        if self._raises:
            raise ModelserverClientError("stub failure")
        assert self._label is not None
        return ModelserverPrediction(
            label=self._label,
            confidence=self._confidence,
            model_version="stub",
            latency_ms=0.0,
        )


@pytest.mark.asyncio
async def test_high_confidence_faq_routes_to_workflow() -> None:
    client = _StubModelserverClient(label="faq", confidence=0.95)
    decision = await route_message_decision("what are your hours?", modelserver_client=client)
    assert decision.route == "rag_search"
    assert decision.label == "faq"
    assert decision.source == "modelserver"


@pytest.mark.asyncio
async def test_spam_label_routes_to_blocked() -> None:
    client = _StubModelserverClient(label="spam", confidence=0.30)
    decision = await route_message_decision("buy crypto now", modelserver_client=client)
    assert decision.route == "blocked"
    assert decision.label == "spam"


@pytest.mark.asyncio
async def test_ambiguous_label_routes_to_agent() -> None:
    client = _StubModelserverClient(label="ambiguous", confidence=0.99)
    decision = await route_message_decision(
        "i'd like pricing and also to compare you with X",
        modelserver_client=client,
    )
    assert decision.route == "agent"
    assert decision.label == "ambiguous"


@pytest.mark.asyncio
async def test_low_confidence_routes_to_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROUTER_CONFIDENCE_THRESHOLD", "0.70")
    client = _StubModelserverClient(label="sales_or_contact", confidence=0.55)
    decision = await route_message_decision("hi there", modelserver_client=client)
    assert decision.route == "agent"
    assert decision.label == "sales_or_contact"
    assert decision.confidence == pytest.approx(0.55)


@pytest.mark.asyncio
async def test_modelserver_unavailable_routes_to_agent() -> None:
    client = _StubModelserverClient(raises=True)
    decision = await route_message_decision("anything", modelserver_client=client)
    assert decision.route == "agent"
    assert "modelserver_unavailable" in decision.reason
    assert decision.source == "modelserver"


@pytest.mark.asyncio
async def test_route_message_returns_string_alias() -> None:
    """The legacy str-returning alias still works (no client -> fallback rules)."""
    assert await route_message("I want to talk to a human") == "escalate"
