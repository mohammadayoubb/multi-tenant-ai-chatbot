# Owner: Nasser
"""Classifier-driven router.

Easy cases should avoid the expensive agent path. The preferred path is the
modelserver classifier; deterministic rules are kept as a safe local fallback
for development and tests when the modelserver/token is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config import get_settings
from app.infra.modelserver import ModelserverClient, ModelserverClientError

RouterRoute = Literal["blocked", "rag_search", "capture_lead", "escalate", "agent"]
RouterLabel = Literal["spam", "faq", "sales_or_contact", "human_request", "ambiguous"]

_MIN_MODEL_CONFIDENCE = 0.65


@dataclass(frozen=True)
class RouteDecision:
    """Structured decision used by ChatService."""

    route: RouterRoute
    label: RouterLabel
    confidence: float
    reason: str
    source: Literal["modelserver", "fallback_rules"]


_LABEL_TO_ROUTE: dict[RouterLabel, RouterRoute] = {
    "spam": "blocked",
    "faq": "rag_search",
    "sales_or_contact": "capture_lead",
    "human_request": "escalate",
    "ambiguous": "agent",
}


async def route_message_decision(
    message: str,
    modelserver_client: ModelserverClient | None = None,
) -> RouteDecision:
    """Return a structured router decision for one inbound visitor message.

    The router tries the trained classifier first. If the classifier is not
    available in local development, deterministic fallback rules keep the chat
    flow usable for demos and tests.

    Low-confidence model predictions fail safe to the bounded agent path.
    """

    cleaned_message = message.strip()
    if not cleaned_message:
        return RouteDecision(
            route="blocked",
            label="spam",
            confidence=1.0,
            reason="Empty visitor message was blocked before routing.",
            source="fallback_rules",
        )

    client = modelserver_client or _default_modelserver_client()

    if client is not None:
        try:
            prediction = await client.predict(cleaned_message)
            if prediction.confidence < _MIN_MODEL_CONFIDENCE:
                return RouteDecision(
                    route="agent",
                    label=prediction.label,
                    confidence=prediction.confidence,
                    reason="Classifier confidence below threshold; failing safe to agent.",
                    source="modelserver",
                )

            return RouteDecision(
                route=_LABEL_TO_ROUTE[prediction.label],
                label=prediction.label,
                confidence=prediction.confidence,
                reason="Classifier selected high-confidence workflow route.",
                source="modelserver",
            )
        except ModelserverClientError:
            # Development/test fallback. Do not log raw visitor text here.
            pass

    return _fallback_rule_decision(cleaned_message)


async def route_message(message: str) -> str:
    """Return the selected route for compatibility with the project contract/tests."""

    decision = await route_message_decision(message)
    return decision.route


def _default_modelserver_client() -> ModelserverClient | None:
    """Create the default classifier client only when a token is configured."""

    settings = get_settings()
    service_token = getattr(settings, "modelserver_service_token", "")
    if not service_token:
        return None

    return ModelserverClient(
        base_url=settings.model_server_url,
        service_token=service_token,
    )


def _fallback_rule_decision(message: str) -> RouteDecision:
    """Keyword fallback used only when the modelserver cannot be used.

    These rules are intentionally conservative. Clear cases stay on the cheap
    workflow path, while mixed or uncertain messages go to the bounded agent.
    """

    lowered = message.lower()

    spam_terms = (
        "buy now",
        "free money",
        "crypto giveaway",
        "casino",
        "viagra",
        "limited time offer",
    )
    human_terms = (
        "human",
        "real person",
        "live person",
        "representative",
        "support team",
        "talk to someone",
        "speak to someone",
        "live agent",
    )
    sales_terms = (
        "price",
        "pricing",
        "quote",
        "contact",
        "demo",
        "sales",
        "call me",
        "email me",
        "book a meeting",
    )
    mixed_or_uncertain_terms = (
        "also",
        "and",
        "but",
        "not sure",
        "maybe",
        "compare",
        "both",
        "while",
    )

    if _contains_any(lowered, spam_terms):
        return RouteDecision(
            route="blocked",
            label="spam",
            confidence=0.80,
            reason="Fallback detected spam terms.",
            source="fallback_rules",
        )

    if _contains_any(lowered, human_terms):
        return RouteDecision(
            route="escalate",
            label="human_request",
            confidence=0.90,
            reason="Fallback detected explicit human handoff request.",
            source="fallback_rules",
        )

    if _contains_any(lowered, sales_terms):
        if _contains_any(lowered, mixed_or_uncertain_terms):
            return RouteDecision(
                route="agent",
                label="ambiguous",
                confidence=0.55,
                reason="Fallback detected mixed sales and multi-step wording.",
                source="fallback_rules",
            )

        return RouteDecision(
            route="capture_lead",
            label="sales_or_contact",
            confidence=0.85,
            reason="Fallback detected sales/contact intent.",
            source="fallback_rules",
        )

    if _contains_any(lowered, mixed_or_uncertain_terms):
        return RouteDecision(
            route="agent",
            label="ambiguous",
            confidence=0.55,
            reason="Fallback detected multi-step or uncertain wording.",
            source="fallback_rules",
        )

    return RouteDecision(
        route="rag_search",
        label="faq",
        confidence=0.75,
        reason="Fallback defaulted to FAQ/RAG path.",
        source="fallback_rules",
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    """Return True when any keyword/phrase exists in the text."""

    return any(term in text for term in terms)