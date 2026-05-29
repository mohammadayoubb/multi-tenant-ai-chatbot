# Owner: Amer
"""Shared Streamlit table helper.

`render_table` is the single entry-point every admin tab uses to render a
tabular list of records. Keeping it in one place means a future swap from
`st.dataframe` to AgGrid (or anything else) doesn't have to be re-applied
across every page.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

import streamlit as st

from admin import _empty


def render_table(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    *,
    filters: Mapping[str, Callable[[Mapping[str, Any]], bool]] | None = None,
    empty_state: Mapping[str, str] | None = None,
    key: str | None = None,
) -> None:
    """Render a Streamlit dataframe with optional filters and empty state.

    Args:
        rows: list of dict-like records.
        columns: explicit column order (subset of keys in ``rows``).
        filters: optional ``{label: predicate}`` map; predicates that return
            ``False`` exclude the row. Filters are evaluated in iteration order.
        empty_state: optional ``{"title": str, "message": str}`` used when
            ``rows`` (after filtering) is empty.
        key: optional unique key to keep multiple tables independent on the
            same page.
    """
    materialized: list[Mapping[str, Any]] = list(rows)
    if filters:
        for predicate in filters.values():
            materialized = [r for r in materialized if predicate(r)]

    if not materialized:
        if empty_state:
            _empty.render_empty_state(
                empty_state.get("title", "Nothing here yet"),
                empty_state.get("message", ""),
            )
        else:
            st.caption("No rows to display.")
        return

    projected = [
        {col: _coerce(row.get(col)) for col in columns} for row in materialized
    ]
    st.dataframe(
        projected,
        width="stretch",
        hide_index=True,
        key=key,
    )


def _coerce(value: Any) -> Any:
    """Coerce non-primitive values to something the dataframe can render."""
    if value is None:
        return "—"
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Iterable):
        return ", ".join(str(v) for v in value)
    return str(value)
