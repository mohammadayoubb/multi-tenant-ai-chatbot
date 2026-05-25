# Owner: Nasser
"""Classifier-driven router.

Easy cases should avoid the expensive agent path.
"""


async def route_message(message: str) -> str:
    """Return the selected route for a visitor message."""
    lowered = message.lower()

    if "human" in lowered or "person" in lowered:
        return "escalate"
    if "price" in lowered or "contact" in lowered:
        return "capture_lead"
    return "rag_search"
