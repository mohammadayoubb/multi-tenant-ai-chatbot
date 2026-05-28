# Owner: Ayoub
"""Classifier evaluator — real, not mock.

Runs the chosen ONNX router classifier (from modelserver/model_card.json)
against the same held-out test split the training notebook used, and emits
macro-F1 to a JSON file the CI threshold checker consumes.

Contract:  specs/006-ci-eval-gates/contracts/eval-cli.md
Threshold: classifier.macro_f1_min (eval_thresholds.yaml)

Determinism (C8): stratified train/test split with random_state=42 + the
ONNX runtime CPU provider both produce byte-identical predictions across
runs, so the emitted macro_f1 is stable for a given (dataset, model) pair.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split

from modelserver.classifier import RouterClassifier

# Match the training notebook's split. Changing either constant requires
# regenerating the model card metrics.
_RANDOM_STATE = 42
_TEST_SIZE = 0.2


def _load_dataset(csv_path: Path) -> tuple[list[str], list[str]]:
    """Return (texts, labels) for every row in the dataset CSV."""
    texts: list[str] = []
    labels: list[str] = []
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            text = row.get("text", "").strip()
            label = row.get("label", "").strip()
            if not text or not label:
                continue
            texts.append(text)
            labels.append(label)
    return texts, labels


def _resolve_repo_root() -> Path:
    """Walk up from this file until we find the project root (pyproject.toml)."""
    here = Path(__file__).resolve()
    for ancestor in [here, *here.parents]:
        if (ancestor / "pyproject.toml").exists():
            return ancestor
    raise RuntimeError("Could not locate repo root (no pyproject.toml found)")


def evaluate(
    *,
    dataset_path: Path | None = None,
    model_card_path: Path | None = None,
) -> dict:
    """Run the classifier eval and return the JSON-shaped result."""
    root = _resolve_repo_root()
    dataset_path = dataset_path or (
        root / "data" / "concierge_combined_public_router_dataset.csv"
    )
    model_card_path = model_card_path or (root / "modelserver" / "model_card.json")

    texts, labels = _load_dataset(dataset_path)
    if not texts:
        raise RuntimeError(f"Dataset is empty: {dataset_path}")

    _, test_texts, _, test_labels = train_test_split(
        texts,
        labels,
        test_size=_TEST_SIZE,
        random_state=_RANDOM_STATE,
        stratify=labels,
    )

    classifier = RouterClassifier(model_card_path=model_card_path)
    predictions = [classifier.predict(text)["label"] for text in test_texts]

    macro_f1 = float(
        f1_score(test_labels, predictions, average="macro", zero_division=0)
    )
    accuracy = float(np.mean(np.array(predictions) == np.array(test_labels)))
    per_class = classification_report(
        test_labels, predictions, output_dict=True, zero_division=0
    )

    with model_card_path.open("r", encoding="utf-8") as fh:
        model_card = json.load(fh)
    dataset_hash = model_card.get("dataset", {}).get("dataset_sha256")

    return {
        "metrics": {
            "macro_f1": macro_f1,
            "accuracy": accuracy,
        },
        "meta": {
            "model_version": classifier.chosen_model,
            "test_size": len(test_texts),
            "random_state": _RANDOM_STATE,
            "per_class_f1": {
                label: per_class[label]["f1-score"]
                for label in classifier.labels
                if label in per_class
            },
        },
        "dataset_hash": f"sha256:{dataset_hash}" if dataset_hash else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--dataset",
        default=None,
        help="Override dataset CSV path (defaults to data/concierge_combined_public_router_dataset.csv).",
    )
    parser.add_argument(
        "--model-card",
        default=None,
        help="Override model card path (defaults to modelserver/model_card.json).",
    )
    args = parser.parse_args(argv)

    print("Evaluating router classifier against held-out test split…", file=sys.stderr)
    result = evaluate(
        dataset_path=Path(args.dataset) if args.dataset else None,
        model_card_path=Path(args.model_card) if args.model_card else None,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        f"classifier.macro_f1 = {result['metrics']['macro_f1']:.4f}  "
        f"(accuracy = {result['metrics']['accuracy']:.4f}, "
        f"n_test = {result['meta']['test_size']})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
