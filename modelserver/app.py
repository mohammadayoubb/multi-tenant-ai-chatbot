# Owner of this file is Ayoub.
# This file defines the lean classifier modelserver API.
# It must stay lightweight: no torch, no transformers, and no training code.

from time import perf_counter
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field


# These are the only labels the router should expect from the classifier.
ClassifierLabel = Literal[
    "spam",
    "faq",
    "sales_or_contact",
    "human_request",
    "ambiguous",
]


class PredictRequest(BaseModel):
    """Request body accepted by the classifier modelserver."""

    message: str = Field(..., min_length=1, max_length=4000)


class PredictResponse(BaseModel):
    """Response returned to the main API/router."""

    label: ClassifierLabel
    confidence: float = Field(..., ge=0.0, le=1.0)
    model_version: str
    latency_ms: float


app = FastAPI(
    title="Concierge Modelserver",
    description="Lean classifier service for routing visitor messages.",
    version="0.1.0",
)


def verify_service_token(authorization: str | None) -> None:
    """Validate service-to-service authentication.

    Temporary placeholder:
    - Later, this token must come from Vault.
    - For now, we only enforce that the header exists and uses Bearer format.
    - We do not hardcode real secrets here.
    """

    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing service authorization header.",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service authorization scheme.",
        )


def classify_message(message: str) -> tuple[ClassifierLabel, float]:
    """Temporary rule-based classifier until the real artifact is connected.

    This keeps the modelserver route testable before training is complete.
    The real implementation will load a joblib or ONNX artifact.
    """

    normalized = message.lower()

    if any(word in normalized for word in ["buy now", "free money", "click here"]):
        return "spam", 0.90

    if any(word in normalized for word in ["price", "pricing", "quote", "book", "appointment"]):
        return "sales_or_contact", 0.85

    if any(word in normalized for word in ["human", "agent", "person", "representative"]):
        return "human_request", 0.88

    if any(word in normalized for word in ["what", "how", "where", "when", "opening hours"]):
        return "faq", 0.80

    return "ambiguous", 0.55


@app.get("/health")
async def health() -> dict[str, str]:
    """Health endpoint used by Docker, CI, and smoke tests."""

    return {
        "status": "ok",
        "service": "modelserver",
        "model_version": "placeholder-v0",
    }


@app.post("/predict", response_model=PredictResponse)
async def predict(
    request: PredictRequest,
    authorization: str | None = Header(default=None),
) -> PredictResponse:
    """Classify one inbound visitor message.

    Important security rule:
    The raw message should not be logged here because it may contain PII,
    secrets, phone numbers, emails, or other sensitive data.
    """

    verify_service_token(authorization)

    start_time = perf_counter()
    label, confidence = classify_message(request.message)
    latency_ms = (perf_counter() - start_time) * 1000

    return PredictResponse(
        label=label,
        confidence=confidence,
        model_version="placeholder-v0",
        latency_ms=round(latency_ms, 3),
    )