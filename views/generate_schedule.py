"""Generate schedule page."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import streamlit as st

from services.schedule_service import (
    generate_schedule,
    get_latest_schedule,
    preflight_check,
    publish_schedule,
    roster_dataframe_rows,
    roster_grid_combined,
)
from services.settings_service import get_operator_name
from utils.session import db_session
from views.roster_display import render_combined_roster


def render() -> None:
    st.title("Generate Schedule")

    col1, col2 = st.columns(2)
    with col1:
        year = st.number_input("Year", 2020, 2035, date.today().year, key="gen_year")
    with col2:
        month = st.number_input("Month", 1, 12, date.today().month, key="gen_month")

    with db_session() as session:
        operator = get_operator_name(session)
        pf = preflight_check(session, year, month)

        st.subheader("Pre-flight Check")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Primary NE Available", "YES" if pf["primary_all_available"] else "NO")
        c2.metric("Backup Available", "YES" if pf["backup_available"] else "NO")
        c3.metric("Active Trainees", pf["trainee_count"])
        mode_label = "IDEAL" if pf["mode"] == "ideal" else "BACKUP / REBALANCED"
        c4.metric("Scheduling Mode", mode_label)

        if st.button("Generate Schedule", type="primary"):
            try:
                sched = generate_schedule(session, year, month, operator)
                session.commit()
                st.session_state["last_schedule_id"] = sched.id
                st.session_state["gen_flash"] = f"Generated version {sched.version}"
                st.rerun()
            except Exception as exc:
                st.error(f"Schedule generation failed: {exc}")

        if st.session_state.get("gen_flash"):
            st.success(st.session_state.pop("gen_flash"))

        sched = get_latest_schedule(session, year, month)
        if sched:
            validation = json.loads(sched.validation_json or "{}")
            explanation = json.loads(sched.explanation_json or "{}")

            st.subheader(f"Schedule v{sched.version} — {sched.status.upper()}")
            st.markdown(f"**Schedule Quality:** {validation.get('quality', sched.quality).upper()}")
            st.markdown(f"**Conflicts:** {len(validation.get('conflicts', []))} | **Warnings:** {len(validation.get('warnings', []))}")

            for c in validation.get("conflicts", []):
                st.error(c)
            for w in validation.get("warnings", []):
                st.warning(w)

            grid_rows, day_nums, nw_days, day_types = roster_grid_combined(session, sched)
            render_combined_roster(grid_rows, day_nums, nw_days, day_types, title="Monthly Duty Roster")

            with st.expander("Day-by-day detail view"):
                rows = roster_dataframe_rows(session, sched)
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            st.subheader("Why this schedule?")
            st.text(explanation.get("text", ""))

            if sched.status == "draft":
                if validation.get("quality") == "conflict":
                    st.error("Cannot publish — resolve conflicts first.")
                else:
                    if validation.get("warnings") and not st.checkbox("Confirm publish despite warnings"):
                        st.info("Review warnings and confirm to publish.")
                    elif st.button("Publish Schedule"):
                        publish_schedule(session, sched.id, operator)
                        st.success("Schedule published.")
                        st.rerun()

        if sched and st.button("Regenerate Schedule"):
            try:
                sched = generate_schedule(session, year, month, operator)
                session.commit()
                st.session_state["gen_flash"] = f"New version {sched.version} created."
                st.rerun()
            except Exception as exc:
                st.error(f"Regeneration failed: {exc}")
