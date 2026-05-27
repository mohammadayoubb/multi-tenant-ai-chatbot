# Owner: Amer
"""Integration tests for admin/usage_page.py.

Spec 005 US4. Covers FR-011 (totals + breakdown + line chart), FR-012 (no
rate-limit / billing controls), FR-013 (non-2xx / transport error →
placeholder).
"""

from __future__ import annotations

from typing import Callable

import httpx
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import admin.usage_page as usage_page


@pytest.fixture
def captured_charts(monkeypatch: pytest.MonkeyPatch) -> list:
    """Capture every st.line_chart(df) call made during render()."""
    calls: list = []
    original = st.line_chart

    def fake_line_chart(data=None, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(data)
        return original(data, *args, **kwargs)

    monkeypatch.setattr(st, "line_chart", fake_line_chart)
    return calls

_ENTRY = "tests/integration/_admin_usage_page_entry.py"

_LIVE_USAGE = {
    "tenant_id": "11111111-1111-1111-1111-111111111111",
    "period": {"start": "2026-05-01T00:00:00Z", "end": "2026-05-27T23:59:59Z"},
    "total_tokens": 1234567,
    "total_cost_usd": 12.34,
    "by_feature": {
        "chat": {"tokens": 500000, "cost_usd": 5.00},
        "embedding": {"tokens": 100000, "cost_usd": 1.00},
        "classifier": {"tokens": 50000, "cost_usd": 0.10},
        "rag": {"tokens": 200000, "cost_usd": 2.00},
        "agent": {"tokens": 350000, "cost_usd": 4.00},
        "guardrails": {"tokens": 34567, "cost_usd": 0.24},
    },
    "daily_cost_usd": [
        {"date": "2026-05-01", "cost_usd": 0.42},
        {"date": "2026-05-02", "cost_usd": 0.51},
        {"date": "2026-05-03", "cost_usd": 0.60},
    ],
}


def _factory(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[[], httpx.Client]:
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return factory


def test_happy_path_renders_totals_breakdown_and_chart(
    monkeypatch: pytest.MonkeyPatch, captured_charts: list
) -> None:
    monkeypatch.setattr(
        usage_page,
        "_http_client",
        _factory(lambda req: httpx.Response(200, json=_LIVE_USAGE)),
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    metrics = [m for m in at.metric]
    labels = [m.label for m in metrics]
    assert "Tokens (month-to-date)" in labels
    assert "Cost USD (month-to-date)" in labels

    rendered = at.dataframe[0].value
    assert len(rendered) == 6
    assert set(rendered["feature"].tolist()) == {
        "chat",
        "embedding",
        "classifier",
        "rag",
        "agent",
        "guardrails",
    }

    # Line chart received 3 datapoints.
    assert len(captured_charts) == 1
    assert len(captured_charts[0]) == 3

    captions = " ".join(c.value for c in at.caption)
    assert "(placeholder)" not in captions


def test_placeholder_fallback_on_404(
    monkeypatch: pytest.MonkeyPatch, captured_charts: list
) -> None:
    monkeypatch.setattr(
        usage_page, "_http_client", _factory(lambda req: httpx.Response(404))
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    captions = " ".join(c.value for c in at.caption) + " ".join(w.value for w in at.warning)
    assert "(placeholder)" in captions
    # Sample data: ≥ 2 datapoints so the chart doesn't degrade.
    assert len(captured_charts) == 1
    assert len(captured_charts[0]) >= 2


@pytest.mark.parametrize("failure", ["status_500", "transport_error"])
def test_server_error_falls_back_to_placeholder(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    secret_marker = "internal-stack-trace-do-not-leak"

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "transport_error":
            raise httpx.ConnectError("connection refused")
        return httpx.Response(500, text=secret_marker)

    monkeypatch.setattr(usage_page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    captions = " ".join(c.value for c in at.caption) + " ".join(w.value for w in at.warning)
    assert "(placeholder)" in captions
    full_output = " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [w.value for w in at.warning]
        + [e.value for e in at.error]
    )
    assert secret_marker not in full_output
    assert "Traceback" not in full_output


def test_missing_feature_defaults_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    partial = dict(_LIVE_USAGE)
    partial["by_feature"] = {
        "chat": {"tokens": 100, "cost_usd": 1.0},
        # embedding, classifier, rag, agent, guardrails missing
    }
    monkeypatch.setattr(
        usage_page,
        "_http_client",
        _factory(lambda req: httpx.Response(200, json=partial)),
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    rendered = at.dataframe[0].value
    assert len(rendered) == 6
    by_feature = dict(zip(rendered["feature"].tolist(), rendered["tokens"].tolist()))
    assert by_feature["chat"] == 100
    for missing in ("embedding", "classifier", "rag", "agent", "guardrails"):
        assert by_feature[missing] == 0


def test_no_mutating_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-012: no rate-limit or billing controls."""
    monkeypatch.setattr(
        usage_page,
        "_http_client",
        _factory(lambda req: httpx.Response(200, json=_LIVE_USAGE)),
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert at.button == []
