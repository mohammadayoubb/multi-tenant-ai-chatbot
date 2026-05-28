"""Classifier loading and prediction logic for the Concierge modelserver.

Owner: Ayoub / Owner C

This module loads the chosen classifier from modelserver/model_card.json.
For the current project decision, the chosen model is the small DL model
exported to ONNX.

Important architecture rules:
- No torch in serving.
- No transformers in serving.
- Training happens only in notebooks.
- The modelserver verifies the artifact SHA-256 before loading it.
- Raw visitor messages should not be logged here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any

import joblib
import numpy as np
import onnxruntime as ort


class ClassifierLoadError(RuntimeError):
    """Raised when the classifier cannot be safely loaded."""


class RouterClassifier:
    """Loads the chosen router classifier and predicts Concierge route labels."""

    def __init__(self, model_card_path: str | Path = "modelserver/model_card.json") -> None:
        self.model_card_path = Path(model_card_path)
        self.base_dir = self.model_card_path.parent.parent

        self.model_card = self._load_model_card()
        self.chosen_model = self.model_card["chosen_model"]

        if self.chosen_model != "small_dl_onnx":
            raise ClassifierLoadError(
                f"Unsupported chosen_model: {self.chosen_model}. "
                "Expected 'small_dl_onnx'."
            )

        self.labels = self.model_card["labels"]
        self.model_info = self.model_card["models_compared"]["small_dl_onnx"]

        self.onnx_path = Path(self.model_info["onnx_artifact"])
        self.vectorizer_path = Path(self.model_info["vectorizer_artifact"])
        self.label_encoder_path = Path(self.model_info["label_encoder_artifact"])

        self._verify_required_file(
            self.onnx_path,
            self.model_info["onnx_artifact_sha256"],
            "ONNX model artifact",
        )
        self._verify_required_file(
            self.vectorizer_path,
            self.model_info["vectorizer_sha256"],
            "TF-IDF vectorizer artifact",
        )
        self._verify_required_file(
            self.label_encoder_path,
            self.model_info["label_encoder_sha256"],
            "Label encoder artifact",
        )

        self.vectorizer = joblib.load(self.vectorizer_path)
        self.label_encoder = joblib.load(self.label_encoder_path)

        self.session = ort.InferenceSession(
            str(self.onnx_path),
            providers=["CPUExecutionProvider"],
        )

        self.input_name = self.session.get_inputs()[0].name

    def predict(self, message: str) -> dict[str, Any]:
        """Predict the router label for one visitor message.

        The model returns one of:
        - spam
        - faq
        - sales_or_contact
        - human_request
        - ambiguous
        """

        start = perf_counter()

        features = self.vectorizer.transform([message]).astype(np.float32)

        # ONNX Runtime expects a dense float32 numpy array.
        dense_features = features.toarray().astype(np.float32)

        logits = self.session.run(None, {self.input_name: dense_features})[0]

        probabilities = self._softmax(logits[0])
        predicted_index = int(np.argmax(probabilities))

        label = str(self.label_encoder.inverse_transform([predicted_index])[0])
        confidence = float(probabilities[predicted_index])

        latency_ms = round((perf_counter() - start) * 1000, 3)

        return {
            "label": label,
            "confidence": confidence,
            "model_version": self.chosen_model,
            "latency_ms": latency_ms,
        }

    def _load_model_card(self) -> dict[str, Any]:
        """Load model_card.json from disk."""

        if not self.model_card_path.exists():
            raise ClassifierLoadError(f"Model card not found: {self.model_card_path}")

        with self.model_card_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _verify_required_file(
        self,
        path: Path,
        expected_sha256: str,
        artifact_name: str,
    ) -> None:
        """Verify that an artifact exists and matches the model card SHA-256."""

        if not path.exists():
            raise ClassifierLoadError(f"{artifact_name} not found: {path}")

        actual_sha256 = self._sha256_file(path)

        if actual_sha256 != expected_sha256:
            raise ClassifierLoadError(
                f"{artifact_name} SHA-256 mismatch. "
                f"Expected {expected_sha256}, got {actual_sha256}."
            )

    @staticmethod
    def _sha256_file(path: Path) -> str:
        """Compute SHA-256 for one file."""

        hash_obj = hashlib.sha256()

        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                hash_obj.update(chunk)

        return hash_obj.hexdigest()

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        """Convert model logits into probabilities."""

        shifted_logits = logits - np.max(logits)
        exp_values = np.exp(shifted_logits)
        return exp_values / np.sum(exp_values)