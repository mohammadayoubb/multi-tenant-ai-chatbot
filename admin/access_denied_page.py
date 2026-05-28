# Owner: Amer
"""Access-denied screen for roles the admin UI does not support.

Reached only via the streamlit_app.py role-router: a successful login whose
JWT carries an unrecognized role lands here instead of any dashboard.
"""

from __future__ import annotations

import streamlit as st

from admin import brand
from admin.auth_state import clear_session


def render() -> None:
    brand.render_card_chrome()
    st.error("Access denied.")
    st.write(
        "Your account doesn't have permission to use the admin console. "
        "Contact your platform administrator if you believe this is a mistake."
    )
    if st.button("Sign out", type="primary", width="stretch"):
        clear_session()
        st.rerun()
