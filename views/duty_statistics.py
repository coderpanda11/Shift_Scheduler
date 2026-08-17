"""Duty statistics page."""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from services.employee_service import list_employees
from services.schedule_service import duty_summary_rows, get_latest_schedule, list_schedules
from utils.session import db_session


def render() -> None:
    st.title("Duty Statistics")

    col1, col2 = st.columns(2)
    with col1:
        year = st.number_input("Year", 2020, 2035, date.today().year, key="stat_year")
    with col2:
        month = st.number_input("Month", 1, 12, date.today().month, key="stat_month")

    with db_session() as session:
        schedules = list_schedules(session, year, month)
        if not schedules:
            st.info("No schedules for this period.")
            return

        version = st.selectbox("Version", [s.version for s in schedules])
        sched = next(s for s in schedules if s.version == version)
        summary = duty_summary_rows(session, sched)

        if not summary:
            st.info("No assignments.")
            return

        df = pd.DataFrame(summary)
        st.dataframe(df, use_container_width=True, hide_index=True)

        fig1 = px.bar(df, x="Employee", y="Total Duties", color="Role", barmode="group")
        st.plotly_chart(fig1, use_container_width=True)

        melt = df.melt(
            id_vars=["Employee", "Role"],
            value_vars=["1st Shift Count", "2nd Shift Count", "3rd Shift Count"],
            var_name="Shift",
            value_name="Count",
        )
        fig2 = px.bar(melt, x="Employee", y="Count", color="Shift", barmode="stack")
        st.plotly_chart(fig2, use_container_width=True)

        role_filter = st.selectbox("Filter by Role", ["All"] + sorted(df["Role"].unique()))
        if role_filter != "All":
            st.dataframe(df[df["Role"] == role_filter], use_container_width=True, hide_index=True)
