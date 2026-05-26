"""FastAPI app for the Concierge classifier modelserver.

Owner: Ayoub / Owner C

This service exposes the trained router classifier over HTTP.
It must stay lean:
- no torch
- no transformers
- no training code
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from modelserver.classifier import ClassifierLoadError, RouterClassifier
from app.infra.service_auth import validate_bearer_token

RouterLabel = Literal[
    "spam",
    "faq",
    "sales_or_contact",
    "human_request",
    "ambiguous",
]


class PredictRequest(BaseModel):
    """Request body for classifier prediction."""

    message: str = Field(..., min_length=1, max_length=4000)


class PredictResponse(BaseModel):
    """Response returned by the modelserver."""

    label: RouterLabel
    confidence: float = Field(..., ge=0.0, le=1.0)
    model_version: str
    latency_ms: float


app = FastAPI(
    title="Concierge Modelserver",
    description="Lean ONNX classifier service for routing visitor messages.",
    version="0.1.0",
)


classifier: RouterClassifier | None = None


def verify_service_auth(authorization: str | None) -> None:
    """Verify service-to-service authentication."""

    expected_token = os.getenv("MODELSERVER_SERVICE_TOKEN")
    result = validate_bearer_token(authorization, expected_token)

    if result.is_valid:
        return

    if result.reason == "Service token is not configured.":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.reason,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=result.reason,
    )


@app.on_event("startup")
async def startup() -> None:
    """Load classifier on startup.

    If artifact hash verification fails, the service should fail to start.
    """

    global classifier

    try:
        classifier = RouterClassifier()
    except ClassifierLoadError as error:
        raise RuntimeError(f"Failed to load classifier: {error}") from error


@app.get("/health")
async def health() -> dict[str, str]:
    """Health endpoint for Docker/CI smoke tests."""

    return {
        "status": "ok",
        "service": "modelserver",
        "model": "small_dl_onnx",
    }


@app.post("/predict", response_model=PredictResponse)
async def predict(
    request: PredictRequest,
    authorization: str | None = Header(default=None),
) -> PredictResponse:
    """Classify one inbound visitor message.

    Security note:
    Do not log the raw message here. It may contain PII or secrets.
    """

    verify_service_auth(authorization)

    if classifier is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Classifier is not loaded.",
        )

    result = classifier.predict(request.message)

    return PredictResponse(**result)