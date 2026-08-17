"""Current schedule view with manual editing and export."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import streamlit as st

from services.employee_service import list_employees
from services.export_service import export_csv, export_excel, export_print_html
from services.schedule_service import (
    duty_summary_rows,
    get_latest_schedule,
    get_schedule,
    list_schedules,
    manual_override_assignment,
    roster_dataframe_rows,
    roster_grid_combined,
)
from services.settings_service import get_operator_name
from utils.session import db_session
from views.roster_display import render_combined_roster


def render() -> None:
    st.title("Current Schedule")

    col1, col2 = st.columns(2)
    with col1:
        year = st.number_input("Year", 2020, 2035, date.today().year, key="cur_year")
    with col2:
        month = st.number_input("Month", 1, 12, date.today().month, key="cur_month")

    with db_session() as session:
        operator = get_operator_name(session)
        schedules = list_schedules(session, year, month)
        if not schedules:
            st.info("No schedule for this month.")
            return

        version = st.selectbox("Version", [s.version for s in schedules], index=0)
        sched = next(s for s in schedules if s.version == version)

        grid_rows, day_nums, nw_days, day_types = roster_grid_combined(session, sched)
        render_combined_roster(grid_rows, day_nums, nw_days, day_types, title="Monthly Duty Roster")

        with st.expander("Day-by-day detail view"):
            st.dataframe(pd.DataFrame(roster_dataframe_rows(session, sched)), use_container_width=True, hide_index=True)

        st.subheader("Manual Edit")
        assign_options = {
            f"{a.date} Shift {a.shift_number} ({a.slot_kind}): {a.employee_name_snapshot}": a.id
            for a in sched.assignments
        }
        selected = st.selectbox("Assignment", list(assign_options.keys()))
        assign_id = assign_options[selected]
        assignment = next(a for a in sched.assignments if a.id == assign_id)

        employees = list_employees(session, active_only=True)
        replace_map = {e.name: e.id for e in employees}
        new_name = st.selectbox("Replace With", list(replace_map.keys()))
        reason = st.text_input("Reason")
        confirm = st.checkbox("Confirm override despite warnings")

        if st.button("Apply Manual Change"):
            _, errors, warnings = manual_override_assignment(
                session, sched.id, assign_id, replace_map[new_name], reason, confirm, operator
            )
            for e in errors:
                st.error(e)
            for w in warnings:
                st.warning(w)
            if not errors and (not warnings or confirm):
                st.success("Assignment updated.")
                st.rerun()

        st.subheader("Export")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button("Export CSV", export_csv(session, sched), file_name=f"roster_{year}_{month:02d}.csv")
        with c2:
            st.download_button("Export Excel", export_excel(session, sched), file_name=f"roster_{year}_{month:02d}.xlsx")
        with c3:
            html = export_print_html(session, sched)
            st.download_button("Print-friendly HTML", html, file_name=f"roster_{year}_{month:02d}.html", mime="text/html")

        st.subheader("Duty Summary")
        st.dataframe(pd.DataFrame(duty_summary_rows(session, sched)), use_container_width=True, hide_index=True)
