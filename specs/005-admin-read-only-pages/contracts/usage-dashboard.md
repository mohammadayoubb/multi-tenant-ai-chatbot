# Contract — Usage Dashboard Page (US4)

**Page**: [admin/usage_page.py](../../../admin/usage_page.py)
**Owner consumed**: Hiba
**Status**: HTTP rollup route is not yet published. This page proposes `GET /tenants/{tenant_id}/usage` for Hiba's handoff.

## Endpoint consumed

### `GET /tenants/{tenant_id}/usage`  *(proposed route — Hiba)*

- **Authoritative source**: backing table [CONTRACT.md §8.1](../../../CONTRACT.md) `tenant_usage`; allowed `feature` vocabulary fixed there.
- **Request**:
  - Method: `GET`
  - Path: `/tenants/{tenant_id}/usage` where `{tenant_id}` is the trusted tenant from the header.
  - Query: optional `period` (e.g., `month_to_date` — backend decides the default; this page renders whatever range the backend returns).
  - Headers: `X-Concierge-Role: tenant_admin`, `X-Concierge-Tenant-Id: <uuid>`, `X-Concierge-Actor-Id: <admin email>`.
- **Expected 200 response** (rollup shape — see [data-model.md §Entity 6](../data-model.md)):
  ```json
  {
    "tenant_id": "uuid",
    "period": {
      "start": "2026-05-01T00:00:00Z",
      "end":   "2026-05-27T23:59:59Z"
    },
    "total_tokens": 1234567,
    "total_cost_usd": 12.34,
    "by_feature": {
      "chat":       { "tokens": 500000, "cost_usd": 5.00 },
      "embedding":  { "tokens": 100000, "cost_usd": 1.00 },
      "classifier": { "tokens":  50000, "cost_usd": 0.10 },
      "rag":        { "tokens": 200000, "cost_usd": 2.00 },
      "agent":      { "tokens": 350000, "cost_usd": 4.00 },
      "guardrails": { "tokens":  34567, "cost_usd": 0.24 }
    },
    "daily_cost_usd": [
      { "date": "2026-05-01", "cost_usd": 0.42 },
      { "date": "2026-05-02", "cost_usd": 0.51 }
    ]
  }
  ```
  - **Required for render**: `total_tokens`, `total_cost_usd`, `by_feature` (with at least one feature key), `daily_cost_usd` (with at least one datapoint for the line chart).
  - **Optional**: `period.start`, `period.end` — rendered as a caption under the totals when present.
- **Placeholder fallback** triggers when (research Decision 5):
  - response status is **any non-2xx** (404, other 4xx, or 5xx), OR
  - response status is 2xx but the body is missing the required fields above, OR
  - the request raises a transport error (`httpx.HTTPError`).
- **Sample data on fallback** (canned in [admin/usage_page.py](../../../admin/usage_page.py)): realistic totals across all six features and 14 daily datapoints so the line chart has enough points to look like a chart (edge case noted in spec — fewer-than-two-point series degrades gracefully).

## Read-only enforcement

This page MUST NOT issue any of: `PUT`, `POST`, `DELETE`, `PATCH`. No rate-limit configuration, no billing controls (FR-012).

## AppTest selectors

| Element | Streamlit widget / key |
|---------|------------------------|
| Total tokens metric | `st.metric` with label `Tokens (month-to-date)` |
| Total cost metric | `st.metric` with label `Cost USD (month-to-date)` |
| Feature breakdown table | `st.dataframe` with key `usage_by_feature_table` |
| Daily cost line chart | `st.line_chart` (page contains exactly one chart) |
| Placeholder badge | `st.caption` or `st.warning` containing the literal text `(placeholder)` |
