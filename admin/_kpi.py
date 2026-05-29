# Owner: Amer
"""Shared Streamlit KPI-row helper.

`render_kpi_row` lays out a list of ``(label, value, delta?)`` tuples as a
side-by-side row of `st.metric` cards. All headline dashboards (TA Overview,
TM Overview, Usage) share the same surface.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

KpiItem = tuple[str, str | int | float] | tuple[str, str | int | float, str | int | float | None]


def render_kpi_row(items: Sequence[KpiItem]) -> None:
    """Render a row of `st.metric` cards.

    Args:
        items: list of ``(label, value)`` or ``(label, value, delta)`` tuples.
            ``delta`` is forwarded to ``st.metric`` and may be ``None``.
    """
    if not items:
        return
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        label = item[0]
        value = item[1]
        delta = item[2] if len(item) >= 3 else None
        with col:
            st.metric(label, value, delta=delta)
