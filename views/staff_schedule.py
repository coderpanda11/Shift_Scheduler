"""Staff view: published team schedule (read-only) + optional my duties."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.employee_service import list_employees
from services.schedule_service import duty_summary_rows, list_schedules, roster_grid_combined
from utils.auth_context import linked_employee_id
from utils.session import db_session
from views.roster_display import render_combined_roster


def render() -> None:
    st.title("Team Schedule")
    st.caption("Published monthly roster — visible to all staff.")

    emp_id = linked_employee_id()

    col1, col2 = st.columns(2)
    with col1:
        year = st.number_input("Year", 2020, 2035, date.today().year, key="staff_year")
    with col2:
        month = st.number_input("Month", 1, 12, date.today().month, key="staff_month")

    with db_session() as session:
        schedules = list_schedules(session, year, month, status="published")
        if not schedules:
            st.info("No published schedule for this month yet.")
            return

        sched = schedules[0]
        st.caption(f"Published version {sched.version}")

        grid_rows, day_nums, nw_days, day_types = roster_grid_combined(session, sched)

        st.subheader("Monthly Duty Roster")
        render_combined_roster(grid_rows, day_nums, nw_days, day_types, title="All Staff")

        if emp_id:
            employees = list_employees(session, active_only=False)
            my_name = next((e.name for e in employees if e.id == emp_id), None)
            if my_name:
                with st.expander(f"My Duties — {my_name}", expanded=False):
                    my_rows = [r for r in grid_rows if r.get("Name") == my_name]
                    if my_rows:
                        render_combined_roster(
                            my_rows, day_nums, nw_days, day_types, title=f"{my_name}"
                        )
                    summary = [
                        row for row in duty_summary_rows(session, sched)
                        if row.get("Employee") == my_name
                    ]
                    if summary:
                        st.dataframe(
                            pd.DataFrame(summary), use_container_width=True, hide_index=True
                        )

        with st.expander("Full duty summary"):
            st.dataframe(
                pd.DataFrame(duty_summary_rows(session, sched)),
                use_container_width=True,
                hide_index=True,
            )
