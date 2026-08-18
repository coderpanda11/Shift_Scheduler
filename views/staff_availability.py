"""Staff view: own availability with personal PIN."""

from __future__ import annotations

from datetime import date

import calendar
import pandas as pd
import streamlit as st

from services.availability_auth_service import (
    employee_requires_avail_pin,
    verify_employee_availability_pin,
)
from services.availability_service import add_availability, delete_availability, list_availability
from services.employee_service import get_employee, list_employees
from utils.auth_context import current_operator, is_staff, linked_employee_id
from utils.session import db_session

STATUSES = ["unavailable", "leave", "training", "official_duty", "other", "available"]


def _employee_labels(employees) -> dict[str, int]:
    return {f"{e.name} ({e.staff_no})": e.id for e in employees}


def _pin_session_key(employee_id: int) -> str:
    return f"avail_pin_unlocked_{employee_id}"


def _render_pin_gate(session, emp_id: int) -> bool:
    """Staff must enter their personal PIN once per session."""
    emp = get_employee(session, emp_id)
    if not emp:
        st.error("Employee not found.")
        return False

    if not employee_requires_avail_pin(emp.role.code):
        return True

    if not emp.availability_pin_hash:
        st.error(
            "No availability PIN set for your account. "
            "Ask DC/In-Charge to set one under Employees."
        )
        return False

    key = _pin_session_key(emp_id)
    if st.session_state.get(key):
        return True

    st.info(
        f"Enter **your personal** availability code for **{emp.name}** "
        f"({emp.staff_no}). This code is unique to you — not shared with other staff."
    )
    with st.form("avail_pin_form"):
        code = st.text_input("Your availability code", type="password")
        if st.form_submit_button("Unlock"):
            if verify_employee_availability_pin(session, emp_id, code):
                st.session_state[key] = True
                st.rerun()
            else:
                st.error("Incorrect availability code.")
    return False


def render() -> None:
    st.title("My Availability")
    linked_id = linked_employee_id()

    with db_session() as session:
        employees = list_employees(session, active_only=True)
        if not employees:
            st.info("No employees found.")
            return

        if is_staff():
            if not linked_id:
                st.warning(
                    "Your login is not linked to an employee record. "
                    "Ask DC/In-Charge to link your account in Settings → Login Users."
                )
                return
            emp = get_employee(session, linked_id)
            if not emp:
                st.error("Linked employee not found.")
                return
            emp_id = linked_id
            st.caption(f"Updating availability for **{emp.name}** ({emp.role.name})")
        else:
            emp_map = _employee_labels(employees)
            selected_label = st.selectbox("Employee", list(emp_map.keys()))
            emp_id = emp_map[selected_label]

        if is_staff() and not _render_pin_gate(session, emp_id):
            return

        tab_add, tab_list = st.tabs(["Add Availability", "My Records"])

        with tab_add:
            with st.form("staff_add_avail"):
                scope = st.radio("Scope", ["Single Date", "Date Range", "Entire Month"])
                col1, col2 = st.columns(2)
                with col1:
                    start = st.date_input("From", value=date.today())
                with col2:
                    end = st.date_input("To", value=date.today())
                if scope == "Entire Month":
                    _, last = calendar.monthrange(start.year, start.month)
                    start = date(start.year, start.month, 1)
                    end = date(start.year, start.month, last)
                elif scope == "Single Date":
                    end = start
                status = st.selectbox("Status", STATUSES)
                reason = st.text_input("Reason")
                if st.form_submit_button("Save"):
                    add_availability(
                        session, emp_id, start, end, status, reason, current_operator()
                    )
                    st.success("Availability saved.")
                    st.rerun()

        with tab_list:
            records = list_availability(session, employee_id=emp_id)
            if records:
                rows = [
                    {
                        "ID": r.id,
                        "From": r.start_date,
                        "To": r.end_date,
                        "Status": r.status,
                        "Reason": r.reason or "",
                    }
                    for r in records
                ]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                del_id = st.number_input("Delete record ID", min_value=0, step=1)
                if st.button("Delete Record") and del_id > 0:
                    owned = next((r for r in records if r.id == int(del_id)), None)
                    if not owned:
                        st.error("Record not found or not yours.")
                    else:
                        delete_availability(session, int(del_id), current_operator())
                        st.rerun()
            else:
                st.info("No availability records.")
