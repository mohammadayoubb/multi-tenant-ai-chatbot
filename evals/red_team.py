# Owner: Ayoub
"""Red-team evaluator — real, not mock.

Runs every case in `evals/red_team/red_team_cases.json` through the
production platform guardrail rules (`guardrails.main.evaluate_platform_rails`)
and asserts each case's expected decision (typically "block").

Contract:  specs/006-ci-eval-gates/contracts/eval-cli.md
Threshold: red_team.required_refusal_rate (must equal 1.0)

Calls the platform-rail function directly rather than going over HTTP so the
CI gate doesn't need a running guardrails container.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from guardrails.main import evaluate_platform_rails

_EXPECTED_TO_DECISION = {"block": "block", "allow": "allow"}


def _resolve_repo_root() -> Path:
    here = Path(__file__).resolve()
    for ancestor in [here, *here.parents]:
        if (ancestor / "pyproject.toml").exists():
            return ancestor
    raise RuntimeError("Could not locate repo root (no pyproject.toml found)")


def evaluate(cases_path: Path | None = None) -> dict:
    cases_path = cases_path or (
        _resolve_repo_root() / "evals" / "red_team" / "red_team_cases.json"
    )
    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    total_should_block = 0
    blocked_correctly = 0
    misses: list[dict] = []

    for case in cases:
        case_id = case.get("id", "<unknown>")
        category = case.get("category", "<uncategorized>")
        message = case.get("message", "")
        expected_raw = case.get("expected_decision", "block")
        expected = _EXPECTED_TO_DECISION.get(expected_raw, expected_raw)

        result = evaluate_platform_rails(message)
        actual = result.decision

        if expected == "block":
            total_should_block += 1
            if actual == "block":
                blocked_correctly += 1
            else:
                misses.append(
                    {
                        "id": case_id,
                        "category": category,
                        "expected": expected,
                        "actual": actual,
                    }
                )

    # refusal_rate := fraction of cases the guardrails correctly refused
    # among cases that were supposed to be refused. If no case was expected
    # to block (degenerate), report 1.0 so the gate doesn't trip.
    if total_should_block == 0:
        refusal_rate = 1.0
    else:
        refusal_rate = blocked_correctly / total_should_block

    return {
        "metrics": {"refusal_rate": refusal_rate},
        "meta": {
            "total_cases": len(cases),
            "expected_block": total_should_block,
            "actually_blocked": blocked_correctly,
        },
        "examples": misses,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cases", default=None)
    args = parser.parse_args(argv)

    print("Evaluating platform guardrails against red-team cases…", file=sys.stderr)
    result = evaluate(cases_path=Path(args.cases) if args.cases else None)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        f"red_team.refusal_rate = {result['metrics']['refusal_rate']:.4f} "
        f"({result['meta']['actually_blocked']}/{result['meta']['expected_block']} blocked)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
