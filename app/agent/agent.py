# Owner: Nasser
"""Bounded tool-calling agent.

The agent must have a max iteration and token budget.
"""


async def run_agent(tenant_id: int, message: str, session_id: str) -> dict:
    """Run the bounded agent path."""
    return {
        "tenant_id": tenant_id,
        "session_id": session_id,
        "answer": "Placeholder agent answer.",
        "message": message,
    }
