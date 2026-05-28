# Owner: Amer
"""Assert a measured eval metric satisfies the threshold in eval_thresholds.yaml.

Contract: specs/006-ci-eval-gates/contracts/threshold-checker.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_THRESHOLDS = REPO_ROOT / "eval_thresholds.yaml"


def _err(msg: str) -> int:
    print(msg, file=sys.stderr)
    return 1


def _direction(metric_key: str) -> tuple[str, str] | None:
    if metric_key.endswith("_min"):
        return "min", metric_key[: -len("_min")]
    if metric_key.startswith("required_"):
        return "eq", metric_key[len("required_"):]
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--metric", required=True)
    parser.add_argument("--json", dest="json_path", required=True)
    parser.add_argument("--thresholds", default=str(DEFAULT_THRESHOLDS))
    args = parser.parse_args(argv)

    thresholds_path = Path(args.thresholds)
    if not thresholds_path.is_file():
        return _err(f"ERROR threshold file not found: {thresholds_path}")
    try:
        thresholds = yaml.safe_load(thresholds_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return _err(f"ERROR could not parse threshold file: {exc}")

    if (
        not isinstance(thresholds, dict)
        or args.gate not in thresholds
        or not isinstance(thresholds[args.gate], dict)
        or args.metric not in thresholds[args.gate]
    ):
        return _err(
            f"ERROR threshold key not found in {thresholds_path}: {args.gate}.{args.metric}"
        )
    threshold_value = thresholds[args.gate][args.metric]

    direction = _direction(args.metric)
    if direction is None:
        return _err(f"ERROR unrecognized threshold key shape: {args.metric}")
    rule, metric_short = direction

    json_path = Path(args.json_path)
    if not json_path.is_file():
        return _err(f"ERROR eval JSON not found: {json_path}")
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _err(f"ERROR could not parse eval JSON: {exc}")

    metrics = payload.get("metrics") if isinstance(payload, dict) else None
    if not isinstance(metrics, dict) or metric_short not in metrics:
        return _err(f"ERROR metric key not found in eval JSON: metrics.{metric_short}")
    measured = metrics[metric_short]
    if isinstance(measured, bool) or not isinstance(measured, (int, float)):
        return _err(f"ERROR metric value is not numeric: {measured!r}")

    label = f"{args.gate}.{metric_short}"
    if rule == "min":
        if measured >= threshold_value:
            print(f"PASS {label}: measured {measured} >= min {threshold_value}")
            return 0
        return _err(f"FAIL {label}: measured {measured} < min {threshold_value}")
    # rule == "eq"
    if measured == threshold_value:
        print(f"PASS {label}: measured {measured} == required {threshold_value}")
        return 0
    return _err(f"FAIL {label}: measured {measured} != required {threshold_value}")


if __name__ == "__main__":
    sys.exit(main())
