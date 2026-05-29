# Owner: Amer
"""Usage dashboard admin page (read-only).

Feature 005 US4 — see specs/005-admin-read-only-pages/.

Shows month-to-date total tokens / cost, a per-feature breakdown across the
six allowed features, and a daily-cost line chart. Read-only: no rate-limit
or billing controls (FR-012). Any non-2xx response, missing-required-field
body, or transport error falls back to canned sample data with a visible
"(placeholder)" caption (FR-013).

Spec 009 US3 T089 — adds a TM aggregate view branch behind a ``role``
parameter. The TM render path lists per-tenant usage with a tenant filter +
the same chart shape; the TA render path is unchanged. Both branches use the
shared ``_kpi`` / ``_table`` helpers so the visual language matches.
"""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd
import streamlit as st

from admin._admin_http import (
    TENANT_ID,
    http_client as _http_client,
    signed_in_tenant_id,
)
from admin._kpi import render_kpi_row
from admin._table import render_table

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
    try:
        with _http_client() as client:
            resp = client.get(f"/tenants/{signed_in_tenant_id()}/usage")
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


def _fetch_tenants() -> tuple[list[dict[str, Any]], bool]:
    try:
        with _http_client() as client:
            resp = client.get("/tenants")
    except httpx.HTTPError:
        return [], True
    if resp.status_code < 200 or resp.status_code >= 300:
        return [], True
    try:
        body = resp.json()
    except ValueError:
        return [], True
    if not isinstance(body, list):
        return [], True
    return body, False


def _fetch_usage_for(tenant_id: str) -> tuple[dict[str, Any], bool]:
    try:
        with _http_client() as client:
            resp = client.get(f"/tenants/{tenant_id}/usage")
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


def _render_tm() -> None:
    """Tenant Manager: per-tenant filter + same headline / breakdown chart."""
    tenants, placeholder = _fetch_tenants()
    if placeholder or not tenants:
        st.caption(
            "(placeholder) — using the sample tenant; backend `GET /tenants` "
            "was unavailable."
        )
        target_id = TENANT_ID
        target_name = "Sample tenant"
    else:
        labels = [f"{t.get('name', '?')} ({t.get('id')})" for t in tenants]
        pick = st.selectbox("Tenant", labels, key="tm_usage_pick")
        selected = tenants[labels.index(pick)]
        target_id = str(selected.get("id", TENANT_ID))
        target_name = str(selected.get("name", "—"))

    usage, usage_placeholder = _fetch_usage_for(target_id)
    if usage_placeholder:
        st.caption("(placeholder)")

    total_tokens = int(usage.get("total_tokens", 0))
    total_cost = float(usage.get("total_cost_usd", 0.0))
    render_kpi_row(
        [
            ("Tenant", target_name),
            ("Tokens (MTD)", f"{total_tokens:,}"),
            ("Cost USD (MTD)", f"${total_cost:.2f}"),
        ]
    )

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
    render_table(
        rows,
        columns=["feature", "tokens", "cost_usd"],
        empty_state={
            "title": "No usage to report",
            "message": "Once this tenant starts handling traffic, per-feature usage will appear here.",
        },
        key="tm_usage_by_feature_table",
    )

    st.markdown("#### Daily cost (USD)")
    daily = usage.get("daily_cost_usd") or []
    if daily:
        chart_df = pd.DataFrame(daily)
        chart_df["date"] = pd.to_datetime(chart_df["date"])
        chart_df = chart_df.set_index("date")
        st.line_chart(chart_df["cost_usd"])
    else:
        st.markdown("_No daily cost data yet._")


def render(*, role: str = "tenant_admin") -> None:
    if role == "tenant_manager":
        _render_tm()
        return
    usage, placeholder = _fetch_usage()
    if placeholder:
        st.caption("(placeholder)")

    total_tokens = int(usage.get("total_tokens", 0))
    total_cost = float(usage.get("total_cost_usd", 0.0))
    render_kpi_row(
        [
            ("Tokens (month-to-date)", f"{total_tokens:,}"),
            ("Cost USD (month-to-date)", f"${total_cost:.2f}"),
        ]
    )

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
    render_table(
        rows,
        columns=["feature", "tokens", "cost_usd"],
        empty_state={
            "title": "No usage to report",
            "message": "Once the agent starts handling traffic, per-feature usage will appear here.",
        },
        key="usage_by_feature_table",
    )

    st.markdown("#### Daily cost (USD)")
    daily = usage.get("daily_cost_usd") or []
    if daily:
        chart_df = pd.DataFrame(daily)
        chart_df["date"] = pd.to_datetime(chart_df["date"])
        chart_df = chart_df.set_index("date")
        st.line_chart(chart_df["cost_usd"])
    else:
        st.markdown("_No daily cost data yet._")
