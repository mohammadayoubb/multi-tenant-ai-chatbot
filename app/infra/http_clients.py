# Owner: Ayoub
"""Service-to-service HTTP clients.

API-to-modelserver and API-to-guardrails calls must be authenticated.
"""


class ServiceClient:
    """Placeholder internal service client."""

    async def post_json(self, url: str, payload: dict) -> dict:
        """Post JSON to an internal service."""
        return {"status": "placeholder"}
