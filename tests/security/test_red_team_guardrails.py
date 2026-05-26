"""Red-team tests for the Concierge guardrails sidecar.

Owner: Ayoub / Owner C

These tests prove that prompt-injection, system-prompt extraction,
and cross-tenant extraction attempts are blocked.

The project CI gate expects red-team pass rate to be 1.0.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from guardrails.main import app


RED_TEAM_CASES_PATH = Path("evals/red_team/red_team_cases.json")


def load_red_team_cases() -> list[dict[str, str]]:
    """Load red-team cases from the eval file."""

    with RED_TEAM_CASES_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def test_red_team_cases_pass() -> None:
    """Every red-team case should match its expected guardrail decision."""

    os.environ["GUARDRAILS_SERVICE_TOKEN"] = "test-token"

    client = TestClient(app)
    cases = load_red_team_cases()

    failures = []

    for case in cases:
        response = client.post(
            "/check",
            headers={"Authorization": "Bearer test-token"},
            json={
                "message": case["message"],
                "tenant_id": "tenant-a",
            },
        )

        if response.status_code != 200:
            failures.append(
                {
                    "id": case["id"],
                    "reason": f"Expected 200, got {response.status_code}",
                }
            )
            continue

        actual_decision = response.json()["decision"]

        if actual_decision != case["expected_decision"]:
            failures.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "message": case["message"],
                    "expected": case["expected_decision"],
                    "actual": actual_decision,
                }
            )

    assert failures == []