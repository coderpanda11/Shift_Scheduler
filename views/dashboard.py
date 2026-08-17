"""Dashboard page."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from services.availability_service import count_unavailable_in_month
from services.calendar_service import calendar_summary
from services.employee_service import list_employees
from services.schedule_service import duty_summary_rows, get_latest_schedule
from utils.session import db_session


def render() -> None:
    st.title("Dashboard")
    today = date.today()
    year, month = today.year, today.month

    col_y, col_m = st.columns(2)
    with col_y:
        year = st.number_input("Year", min_value=2020, max_value=2035, value=year, key="dash_year")
    with col_m:
        month = st.number_input("Month", min_value=1, max_value=12, value=month, key="dash_month")

    with db_session() as session:
        employees = list_employees(session, active_only=True)
        cal = calendar_summary(session, year, month)
        unavailable = count_unavailable_in_month(session, year, month)
        sched = get_latest_schedule(session, year, month)

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Active Employees", len(employees))
        c2.metric("Working Days", cal["working_days"])
        c3.metric("Non-Working Days", cal["non_working_days"])
        c4.metric("Total Scheduled Duties", len(sched.assignments) if sched else 0)
        c5.metric("Unavailable (month)", unavailable)
        status = sched.status.upper() if sched else "NONE"
        c6.metric("Schedule Status", status)

        if sched:
            validation = json.loads(sched.validation_json or "{}")
            quality = validation.get("quality", sched.quality).upper()
            st.info(f"Schedule Quality: **{quality}** — v{sched.version} ({sched.scheduling_mode})")

            summary = duty_summary_rows(session, sched)
            if summary:
                df = pd.DataFrame(summary)
                st.subheader("Shift Distribution")
                display_cols = ["Employee", "Role", "1st Shift Count", "2nd Shift Count", "3rd Shift Count", "Total Duties"]
                st.dataframe(
                    df[display_cols].style.apply(_highlight_imbalance, axis=None),
                    use_container_width=True,
                    hide_index=True,
                )

                st.subheader("Duty Distribution Chart")
                fig = px.bar(df, x="Employee", y="Total Duties", color="Role", title="Employee vs Total Duties")
                fig.update_layout(showlegend=True, height=400)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No schedule generated for this month yet. Go to **Generate Schedule**.")


def _highlight_imbalance(df: pd.DataFrame):
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    if "Total Duties" in df.columns and len(df) > 1:
        diff = df["Total Duties"].max() - df["Total Duties"].min()
        if diff > 1:
            styles.loc[df["Total Duties"] == df["Total Duties"].max(), "Total Duties"] = (
                "background-color: #fecaca"
            )
    return styles
