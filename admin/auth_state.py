# Owner: Amer
"""Streamlit session-state helpers for admin authentication.

The admin JWT lives in `st.session_state["admin_token"]` only. Streamlit
session state is held server-side in the python process — it never reaches
the browser localStorage / cookies, which matches the storage discipline the
widget enforces.

Companion fields (`admin_actor_id`, `admin_tenant_id`, `admin_role`) are
populated from the login response so the page chrome can show "Signed in as…"
without re-decoding the JWT on every render.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def is_authenticated() -> bool:
    return bool(st.session_state.get("admin_token"))


def get_token() -> str | None:
    token = st.session_state.get("admin_token")
    return token if isinstance(token, str) and token else None


def get_actor_id() -> str | None:
    actor = st.session_state.get("admin_actor_id")
    return actor if isinstance(actor, str) and actor else None


def get_tenant_id() -> str | None:
    tenant = st.session_state.get("admin_tenant_id")
    return tenant if isinstance(tenant, str) and tenant else None


def get_role() -> str | None:
    role = st.session_state.get("admin_role")
    return role if isinstance(role, str) and role else None


def get_full_name() -> str | None:
    name = st.session_state.get("admin_full_name")
    return name if isinstance(name, str) and name else None


def set_session(login_body: dict[str, Any]) -> None:
    """Persist login response fields into st.session_state.

    Every field below is trusted because it came from the server-issued login
    response (which itself derived them from the verified password and the
    admin_users row). The frontend NEVER lets the user pick role or tenant_id.
    """
    st.session_state["admin_token"] = login_body["token"]
    st.session_state["admin_actor_id"] = login_body.get("actor_id")
    st.session_state["admin_tenant_id"] = login_body.get("tenant_id")
    st.session_state["admin_role"] = login_body.get("role")
    st.session_state["admin_full_name"] = login_body.get("full_name")


def clear_session() -> None:
    """Wipe every admin-session key from st.session_state."""
    for key in (
        "admin_token",
        "admin_actor_id",
        "admin_tenant_id",
        "admin_role",
        "admin_full_name",
    ):
        st.session_state.pop(key, None)
