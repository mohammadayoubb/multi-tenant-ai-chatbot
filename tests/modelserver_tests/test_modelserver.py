"""Tests for the Concierge modelserver.

Owner: Ayoub / Owner C

These tests verify that:
- the health endpoint works
- /predict requires service authentication
- /predict rejects invalid service credentials
- /predict returns a valid router label when authenticated
"""

import os

from fastapi.testclient import TestClient

from modelserver.app import app


VALID_LABELS = {
    "spam",
    "faq",
    "sales_or_contact",
    "human_request",
    "ambiguous",
}


def test_modelserver_health() -> None:
    """Health endpoint should confirm that the modelserver is running."""

    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "modelserver"


def test_predict_rejects_missing_auth() -> None:
    """Prediction should fail when no Authorization header is provided."""

    os.environ["MODELSERVER_SERVICE_TOKEN"] = "test-token"

    client = TestClient(app)

    response = client.post(
        "/predict",
        json={"message": "What are your opening hours?"},
    )

    assert response.status_code == 401


def test_predict_rejects_invalid_auth() -> None:
    """Prediction should fail when the Authorization token is wrong."""

    os.environ["MODELSERVER_SERVICE_TOKEN"] = "test-token"

    client = TestClient(app)

    response = client.post(
        "/predict",
        headers={"Authorization": "Bearer wrong-token"},
        json={"message": "What are your opening hours?"},
    )

    assert response.status_code == 401


def test_predict_returns_valid_router_label() -> None:
    """Prediction should return one of the allowed Concierge router labels."""

    os.environ["MODELSERVER_SERVICE_TOKEN"] = "test-token"

    with TestClient(app) as client:
        response = client.post(
            "/predict",
            headers={"Authorization": "Bearer test-token"},
            json={"message": "What are your opening hours?"},
        )

    assert response.status_code == 200

    body = response.json()

    assert body["label"] in VALID_LABELS
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["model_version"] == "small_dl_onnx"
    assert body["latency_ms"] >= 0