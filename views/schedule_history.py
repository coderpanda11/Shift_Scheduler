"""Schedule history page."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import streamlit as st

from services.employee_service import list_employees, list_roles
from services.schedule_service import (
    get_schedule,
    list_schedules,
    roster_dataframe_rows,
    roster_grid_combined,
)
from utils.session import db_session
from views.roster_display import render_combined_roster


def render() -> None:
    st.title("Schedule History")

    with db_session() as session:
        all_schedules = list_schedules(session)
        if not all_schedules:
            st.info("No historical schedules.")
            return

        years = sorted({s.year for s in all_schedules}, reverse=True)
        year = st.selectbox("Year", ["All"] + years)
        months = sorted({s.month for s in all_schedules if year == "All" or s.year == year})
        month = st.selectbox("Month", ["All"] + months)
        roles = list_roles(session)
        role_filter = st.selectbox("Role", ["All"] + [r.name for r in roles])
        employees = list_employees(session)
        emp_filter = st.selectbox("Employee", ["All"] + [e.name for e in employees])
        versions = sorted({s.version for s in all_schedules}, reverse=True)
        version_filter = st.selectbox("Version", ["All"] + versions)

        filtered = all_schedules
        if year != "All":
            filtered = [s for s in filtered if s.year == year]
        if month != "All":
            filtered = [s for s in filtered if s.month == month]
        if version_filter != "All":
            filtered = [s for s in filtered if s.version == version_filter]

        rows = [
            {
                "ID": s.id,
                "Period": f"{s.month:02d}/{s.year}",
                "Version": s.version,
                "Status": s.status,
                "Mode": s.scheduling_mode,
                "Quality": s.quality,
                "Created": s.created_at.strftime("%Y-%m-%d %H:%M"),
                "By": s.created_by,
            }
            for s in filtered
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        sched_id = st.number_input("Open Schedule ID", min_value=0, step=1)
        if sched_id > 0 and st.button("View Schedule"):
            sched = get_schedule(session, int(sched_id))
            if sched:
                st.markdown(f"### {sched.month:02d}/{sched.year} v{sched.version} ({sched.status})")
                if emp_filter != "All":
                    assigns = [a for a in sched.assignments if a.employee_name_snapshot == emp_filter]
                    st.write(f"Assignments for {emp_filter}: {len(assigns)}")
                if role_filter != "All":
                    assigns = [a for a in sched.assignments if role_filter in a.role_snapshot]
                    st.write(f"Assignments for role {role_filter}: {len(assigns)}")
                grid_rows, day_nums, nw_days, day_types = roster_grid_combined(session, sched)
                render_combined_roster(grid_rows, day_nums, nw_days, day_types, title="Monthly Duty Roster")
                with st.expander("Day-by-day detail view"):
                    st.dataframe(pd.DataFrame(roster_dataframe_rows(session, sched)), use_container_width=True, hide_index=True)
                explanation = json.loads(sched.explanation_json or "{}")
                with st.expander("Why this schedule?"):
                    st.text(explanation.get("text", ""))
            else:
                st.error("Schedule not found.")
