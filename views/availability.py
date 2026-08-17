"""Availability management page."""

from __future__ import annotations

from datetime import date

import calendar
import pandas as pd
import streamlit as st

from services.availability_service import (
    add_availability,
    availability_affects_schedules,
    delete_availability,
    list_availability,
)
from services.employee_service import list_employees
from services.settings_service import get_operator_name
from utils.session import db_session

STATUSES = ["unavailable", "leave", "training", "official_duty", "other", "available"]


def render() -> None:
    st.title("Availability / Leave")

    with db_session() as session:
        operator = get_operator_name(session)
        employees = list_employees(session, active_only=True)
        emp_map = {f"{e.name} ({e.staff_no})": e.id for e in employees}

        if availability_affects_schedules(session, date.today().year, date.today().month):
            st.warning("Schedule is affected. **Regeneration recommended.**")
            if st.button("Go to Generate Schedule"):
                st.session_state["nav"] = "Generate Schedule"
                st.rerun()

        tab_add, tab_list = st.tabs(["Add Availability", "Current Records"])

        with tab_add:
            with st.form("add_avail"):
                emp = st.selectbox("Employee", list(emp_map.keys()))
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
                    add_availability(session, emp_map[emp], start, end, status, reason, operator)
                    st.success("Availability saved. Schedule is affected — regeneration recommended.")
                    st.rerun()

        with tab_list:
            records = list_availability(session)
            if records:
                rows = []
                for r in records:
                    emp = next((e for e in employees if e.id == r.employee_id), None)
                    rows.append({
                        "ID": r.id,
                        "Employee": emp.name if emp else r.employee_id,
                        "From": r.start_date,
                        "To": r.end_date,
                        "Status": r.status,
                        "Reason": r.reason or "",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                del_id = st.number_input("Delete record ID", min_value=0, step=1)
                if st.button("Delete Record") and del_id > 0:
                    delete_availability(session, int(del_id), operator)
                    st.rerun()
            else:
                st.info("No availability records.")
