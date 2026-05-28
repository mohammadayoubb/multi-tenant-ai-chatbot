# Owner: Amer
"""Usage dashboard admin page (read-only).

Feature 005 US4 — see specs/005-admin-read-only-pages/.

Shows month-to-date total tokens / cost, a per-feature breakdown across the
six allowed features, and a daily-cost line chart. Read-only: no rate-limit
or billing controls (FR-012). Any non-2xx response, missing-required-field
body, or transport error falls back to canned sample data with a visible
"(placeholder)" caption (FR-013).
"""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd
import streamlit as st

from admin._admin_http import TENANT_ID, http_client as _http_client
from admin._admin_http import tenant_id as _tenant_id

_FEATURES = ["chat", "embedding", "classifier", "rag", "agent", "guardrails"]
_REQUIRED_FIELDS = ("total_tokens", "total_cost_usd", "by_feature", "daily_cost_usd")

_SAMPLE_USAGE: dict[str, Any] = {
    "tenant_id": TENANT_ID,
    "period": {"start": "2026-05-01T00:00:00Z", "end": "2026-05-27T23:59:59Z"},
    "total_tokens": 950_000,
    "total_cost_usd": 9.87,
    "by_feature": {
        "chat": {"tokens": 400_000, "cost_usd": 4.00},
        "embedding": {"tokens": 90_000, "cost_usd": 0.90},
        "classifier": {"tokens": 40_000, "cost_usd": 0.08},
        "rag": {"tokens": 150_000, "cost_usd": 1.50},
        "agent": {"tokens": 250_000, "cost_usd": 3.20},
        "guardrails": {"tokens": 20_000, "cost_usd": 0.19},
    },
    "daily_cost_usd": [
        {"date": f"2026-05-{d:02d}", "cost_usd": round(0.30 + 0.02 * d, 2)}
        for d in range(1, 15)
    ],
}


def _fetch_usage() -> tuple[dict[str, Any], bool]:
    current_tenant_id = _tenant_id()
    try:
        with _http_client() as client:
            resp = client.get(f"/tenants/{current_tenant_id}/usage")
    except httpx.HTTPError:
        return _SAMPLE_USAGE, True
    if resp.status_code < 200 or resp.status_code >= 300:
        return _SAMPLE_USAGE, True
    try:
        body = resp.json()
    except ValueError:
        return _SAMPLE_USAGE, True
    if not isinstance(body, dict) or not all(k in body for k in _REQUIRED_FIELDS):
        return _SAMPLE_USAGE, True
    return body, False


def render() -> None:
    usage, placeholder = _fetch_usage()
    if placeholder:
        st.caption("(placeholder)")

    total_tokens = int(usage.get("total_tokens", 0))
    total_cost = float(usage.get("total_cost_usd", 0.0))
    cols = st.columns(2)
    cols[0].metric("Tokens (month-to-date)", f"{total_tokens:,}")
    cols[1].metric("Cost USD (month-to-date)", f"${total_cost:.2f}")

    period = usage.get("period") or {}
    if period.get("start") and period.get("end"):
        st.caption(f"{period['start']} → {period['end']}")

    st.markdown("#### Breakdown by feature")
    by_feature = usage.get("by_feature") or {}
    rows = [
        {
            "feature": feature,
            "tokens": int((by_feature.get(feature) or {}).get("tokens", 0)),
            "cost_usd": float((by_feature.get(feature) or {}).get("cost_usd", 0.0)),
        }
        for feature in _FEATURES
    ]
    st.dataframe(rows, key="usage_by_feature_table", width="stretch")

    st.markdown("#### Daily cost (USD)")
    daily = usage.get("daily_cost_usd") or []
    if daily:
        chart_df = pd.DataFrame(daily)
        chart_df["date"] = pd.to_datetime(chart_df["date"])
        chart_df = chart_df.set_index("date")
        st.line_chart(chart_df["cost_usd"])
    else:
        st.markdown("_No daily cost data yet._")
