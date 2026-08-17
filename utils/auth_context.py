"""Auth helpers for views."""

from __future__ import annotations

import streamlit as st


def current_operator(fallback: str = "DC/In-Charge") -> str:
    user = st.session_state.get("auth_user")
    if user:
        return user.get("display_name") or fallback
    return fallback


def is_admin() -> bool:
    user = st.session_state.get("auth_user") or {}
    return user.get("role") == "admin"


def is_staff() -> bool:
    user = st.session_state.get("auth_user") or {}
    return user.get("role") == "staff"


def is_dc_incharge() -> bool:
    user = st.session_state.get("auth_user") or {}
    return user.get("role") == "dc_incharge"


def linked_employee_id() -> int | None:
    user = st.session_state.get("auth_user") or {}
    emp_id = user.get("employee_id")
    return int(emp_id) if emp_id else None
