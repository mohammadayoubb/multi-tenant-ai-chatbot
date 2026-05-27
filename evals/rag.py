# Owner: Nasser (TEMPORARY MOCK by Amer, 2026-05-27 — replace with real RAG evaluator)
"""Mock RAG evaluator. Replace with real measurement CLI.

Contract: specs/006-ci-eval-gates/contracts/eval-cli.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    print("MOCK EVALUATOR: rag is not yet implemented — owner: Nasser", file=sys.stderr)

    payload = {"metrics": {"hit_at_5": 0.75, "faithfulness": 0.80}, "_mock": True}
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
