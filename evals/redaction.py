# Owner: Ayoub
"""Redaction evaluator — real, not mock.

Runs every case in `evals/redaction/redaction_cases.json` through the
production `redact_text` function and counts how many cases leaked any of
their `must_not_contain` strings into the redacted output.

Contract:  specs/006-ci-eval-gates/contracts/eval-cli.md
Threshold: redaction.required_secret_leak_count (must equal 0)

Deterministic by construction — `redact_text` is pure regex substitution.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.infra.redaction import redact_text


def _resolve_repo_root() -> Path:
    here = Path(__file__).resolve()
    for ancestor in [here, *here.parents]:
        if (ancestor / "pyproject.toml").exists():
            return ancestor
    raise RuntimeError("Could not locate repo root (no pyproject.toml found)")


def evaluate(cases_path: Path | None = None) -> dict:
    """Run the redaction eval and return the JSON-shaped result."""
    cases_path = cases_path or (
        _resolve_repo_root() / "evals" / "redaction" / "redaction_cases.json"
    )
    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    leaks: list[dict] = []
    for case in cases:
        case_id = case.get("id", "<unknown>")
        category = case.get("category", "<uncategorized>")
        text_in = case.get("input", "")
        forbidden = case.get("must_not_contain", [])

        redacted = redact_text(text_in)
        leaked = [token for token in forbidden if token in redacted]
        if leaked:
            leaks.append(
                {
                    "id": case_id,
                    "category": category,
                    "leaked": leaked,
                    "redacted": redacted,
                }
            )

    return {
        "metrics": {"secret_leak_count": len(leaks)},
        "meta": {
            "total_cases": len(cases),
            "leaked_cases": len(leaks),
        },
        "examples": leaks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cases", default=None)
    args = parser.parse_args(argv)

    print("Evaluating redaction against committed cases…", file=sys.stderr)
    result = evaluate(cases_path=Path(args.cases) if args.cases else None)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        f"redaction.secret_leak_count = {result['metrics']['secret_leak_count']} "
        f"of {result['meta']['total_cases']} cases",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
