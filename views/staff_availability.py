"""Staff view: own availability only."""

from __future__ import annotations

from datetime import date

import calendar
import pandas as pd
import streamlit as st

from services.availability_service import add_availability, delete_availability, list_availability
from services.employee_service import list_employees
from utils.auth_context import current_operator, is_staff, linked_employee_id
from utils.session import db_session

STATUSES = ["unavailable", "leave", "training", "official_duty", "other", "available"]


def _employee_labels(employees) -> dict[str, int]:
    return {f"{e.name} ({e.staff_no})": e.id for e in employees}


def render() -> None:
    st.title("My Availability")
    linked_id = linked_employee_id()

    with db_session() as session:
        employees = list_employees(session, active_only=True)
        if not employees:
            st.info("No employees found.")
            return

        emp_map = _employee_labels(employees)
        labels = list(emp_map.keys())
        default_idx = 0
        if linked_id:
            for i, label in enumerate(labels):
                if emp_map[label] == linked_id:
                    default_idx = i
                    break

        selected_label = st.selectbox("Employee", labels, index=default_idx)
        emp_id = emp_map[selected_label]

        if is_staff():
            if not linked_id:
                st.warning(
                    "Your login is not linked to an employee record. "
                    "Ask DC/In-Charge to link your account in Settings → Login Users."
                )
                return
            if emp_id != linked_id:
                st.error("You can only add or view availability for your own employee record.")
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
