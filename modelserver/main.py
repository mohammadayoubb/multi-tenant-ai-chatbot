# Owner: Ayoub
"""Lean classifier model server.

This service must use onnxruntime or scikit-learn/joblib only.
No torch or transformers are allowed in this container.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Concierge Model Server")


class ClassifyRequest(BaseModel):
    """Inbound message classification request."""

    text: str


class ClassifyResponse(BaseModel):
    """Inbound message classification response."""

    label: str
    confidence: float


@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest) -> ClassifyResponse:
    """Classify a visitor message into an intent."""
    return ClassifyResponse(label="faq", confidence=0.80)
