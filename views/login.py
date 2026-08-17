"""Login page."""

from __future__ import annotations

import streamlit as st

from services.auth_service import authenticate
from utils.session import db_session


def render() -> None:
    st.markdown(
        """
        <div class="login-banner">
            <div class="logo-slot">LOGO</div>
            <div>
                <h2>Duty Roster Management System</h2>
                <p>Please sign in to continue</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with db_session() as session:
        with st.form("login_form"):
            username = st.text_input("Login ID / Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Sign In", type="primary", use_container_width=True):
                if not username.strip() or not password:
                    st.error("Enter username and password.")
                else:
                    user = authenticate(session, username, password)
                    if not user:
                        st.error("Invalid login ID or password.")
                    else:
                        st.session_state["auth_user"] = {
                            "id": user.id,
                            "username": user.username,
                            "display_name": user.display_name,
                            "role": user.role,
                            "employee_id": user.employee_id,
                        }
                        st.rerun()

        st.caption("Default DC/In-Charge: **dc_incharge** / **DcIncharge@123**")
