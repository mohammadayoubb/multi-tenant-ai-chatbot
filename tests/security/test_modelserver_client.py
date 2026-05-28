"""Tests for the modelserver HTTP client adapter.

Owner: Ayoub / Owner C
"""

from __future__ import annotations

import pytest

from app.infra.modelserver import (
    ModelserverClient,
    ModelserverClientError,
)


class FakeResponse:
    """Small fake HTTP response for client tests."""

    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        """Return fake JSON response body."""

        return self._payload


class FakeAsyncClient:
    """Fake httpx.AsyncClient replacement."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(
        self,
        url: str,
        headers: dict[str, str],
        json: dict[str, str],
    ) -> FakeResponse:
        assert url == "http://modelserver:8001/predict"
        assert headers["Authorization"] == "Bearer test-token"
        assert "message" in json

        return FakeResponse(
            status_code=200,
            payload={
                "label": "faq",
                "confidence": 0.91,
                "model_version": "small_dl_onnx",
                "latency_ms": 2.5,
            },
        )


class FakeFailingAsyncClient(FakeAsyncClient):
    """Fake client returning a failed response."""

    async def post(
        self,
        url: str,
        headers: dict[str, str],
        json: dict[str, str],
    ) -> FakeResponse:
        return FakeResponse(
            status_code=401,
            payload={"detail": "Invalid service credentials."},
        )


@pytest.mark.asyncio
async def test_modelserver_client_returns_prediction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client should return a structured prediction."""

    import app.infra.modelserver as modelserver_module

    monkeypatch.setattr(modelserver_module.httpx, "AsyncClient", FakeAsyncClient)

    client = ModelserverClient(
        base_url="http://modelserver:8001",
        service_token="test-token",
    )

    prediction = await client.predict("What are your opening hours?")

    assert prediction.label == "faq"
    assert prediction.confidence == 0.91
    assert prediction.model_version == "small_dl_onnx"
    assert prediction.latency_ms == 2.5


@pytest.mark.asyncio
async def test_modelserver_client_requires_service_token() -> None:
    """Client should fail if the service token is missing."""

    client = ModelserverClient(
        base_url="http://modelserver:8001",
        service_token="",
    )

    with pytest.raises(ModelserverClientError):
        await client.predict("What are your opening hours?")


@pytest.mark.asyncio
async def test_modelserver_client_raises_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client should fail when modelserver returns non-200."""

    import app.infra.modelserver as modelserver_module

    monkeypatch.setattr(modelserver_module.httpx, "AsyncClient", FakeFailingAsyncClient)

    client = ModelserverClient(
        base_url="http://modelserver:8001",
        service_token="test-token",
    )

    with pytest.raises(ModelserverClientError):
        await client.predict("What are your opening hours?")