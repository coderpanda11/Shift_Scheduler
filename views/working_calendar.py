"""Working calendar and holidays page."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.calendar_service import (
    add_holiday,
    calendar_summary,
    delete_holiday,
    list_holidays,
    remove_date_override,
    set_date_override,
)
from services.settings_service import get_operator_name, get_saturday_rule
from utils.session import db_session

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def render() -> None:
    st.title("Working Calendar")

    col_y, col_m = st.columns(2)
    with col_y:
        year = st.number_input("Year", 2020, 2035, date.today().year, key="cal_year")
    with col_m:
        month = st.number_input("Month", 1, 12, date.today().month, key="cal_month")

    with db_session() as session:
        operator = get_operator_name(session)
        cal = calendar_summary(session, year, month)
        sat_rule = get_saturday_rule(session)
        if sat_rule == "first_third_off":
            st.info("Calendar rule: **Sunday** off · **1st & 3rd Saturday** off · **2nd/4th/5th Saturday** working")

        st.metric("Working / Non-Working", f"{cal['working_days']} / {cal['non_working_days']}")

        rows = [
            {
                "Date": d.date.strftime("%d-%m-%Y"),
                "Day": d.day_name,
                "Type": d.day_type,
                "Status": "Working" if d.is_working else "Non-Working",
            }
            for d in cal["days"]
        ]
        df = pd.DataFrame(rows)
        st.dataframe(
            df.style.apply(lambda x: ["background-color: #fef3c7" if v == "NW" else "" for v in x], subset=["Type"]),
            use_container_width=True,
            hide_index=True,
        )

        tab_hol, tab_override = st.tabs(["Holidays", "Manual Date Override"])

        with tab_hol:
            with st.form("add_holiday"):
                hdate = st.date_input("Holiday Date")
                hname = st.text_input("Holiday Name")
                yearly = st.checkbox("Repeats Yearly")
                if st.form_submit_button("Add Holiday"):
                    add_holiday(session, hdate, hname, yearly, operator)
                    st.rerun()
            holidays = list_holidays(session)
            if holidays:
                for h in holidays:
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"{h.date} — {h.name} {'(yearly)' if h.repeats_yearly else ''}")
                    if c2.button("Delete", key=f"del_h_{h.id}"):
                        delete_holiday(session, h.id, operator)
                        st.rerun()

        with tab_override:
            with st.form("override"):
                odate = st.date_input("Date", key="ov_date")
                status = st.radio("Set as", ["Working Day", "Non-Working Day"])
                reason = st.text_input("Reason")
                if st.form_submit_button("Apply Override"):
                    set_date_override(session, odate, status == "Working Day", reason, operator)
                    st.rerun()
            if st.button("Remove Override for Selected Date"):
                remove_date_override(session, odate)
                st.rerun()
