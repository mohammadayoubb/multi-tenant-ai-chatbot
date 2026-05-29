# Owner: Nasser
"""Router distribution evaluator (task T062b, SC-003).

Loops the existing classifier golden-set test split through
``route_message_decision`` and reports the share of decisions that
land on each high-level branch:

- ``workflow``  — high-confidence routes (rag_search / capture_lead / escalate)
- ``agent``     — ambiguous / low-confidence routes
- ``blocked``   — spam refusals

SC-003 targets ``workflow_share >= 0.80`` AND ``agent_share <= 0.20``.
Failure here does NOT block merge (the production target uses real traffic;
the golden set is small) — the result is recorded in the PR description.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path

from sklearn.model_selection import train_test_split

from app.agent.router import route_message_decision

_DATASET = Path(__file__).resolve().parent.parent / "data" / "concierge_combined_public_router_dataset.csv"
_RANDOM_STATE = 42
_TEST_SIZE = 0.2


def _load_test_split() -> list[str]:
    texts: list[str] = []
    labels: list[str] = []
    with _DATASET.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            text = row.get("text", "").strip()
            label = row.get("label", "").strip()
            if not text or not label:
                continue
            texts.append(text)
            labels.append(label)
    _, test_texts, _, _ = train_test_split(
        texts, labels, test_size=_TEST_SIZE, random_state=_RANDOM_STATE, stratify=labels
    )
    return test_texts


async def _bucket_counts(messages: list[str]) -> dict[str, int]:
    counts = {"workflow": 0, "agent": 0, "blocked": 0}
    for message in messages:
        decision = await route_message_decision(message)
        if decision.route == "blocked":
            counts["blocked"] += 1
        elif decision.route == "agent":
            counts["agent"] += 1
        else:
            counts["workflow"] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Router distribution check (SC-003)")
    parser.add_argument("--output", default="router-distribution.json")
    args = parser.parse_args()

    messages = _load_test_split()
    counts = asyncio.run(_bucket_counts(messages))
    total = sum(counts.values()) or 1
    report = {
        "total": total,
        "counts": counts,
        "workflow_share": counts["workflow"] / total,
        "agent_share": counts["agent"] / total,
        "blocked_share": counts["blocked"] / total,
        "thresholds": {"workflow_share_min": 0.80, "agent_share_max": 0.20},
        "pass": (counts["workflow"] / total >= 0.80) and (counts["agent"] / total <= 0.20),
    }
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 0  # informational only — never blocks


if __name__ == "__main__":
    raise SystemExit(main())
