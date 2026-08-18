"""VPS Team — separate DC and DR shift schedulers."""

from __future__ import annotations

import calendar
import json
from datetime import date

import pandas as pd
import streamlit as st

from config import VPS_SITE_DC, VPS_SITE_DR
from services.settings_service import get_operator_name
from utils.auth_context import current_operator
from services.vps_service import (
    add_vps_availability,
    add_vps_member,
    deactivate_vps_member,
    delete_vps_availability,
    generate_vps_schedule,
    list_vps_availability,
    list_vps_members,
    list_vps_schedules,
    publish_vps_schedule,
    update_vps_member,
    vps_roster_grid,
)
from utils.session import db_session
from views.roster_display import render_combined_roster

STATUSES = ["unavailable", "leave", "training", "official_duty", "other", "available"]


def _render_site_schedule(session, site: str, site_label: str, year: int, month: int, operator: str) -> None:
    st.subheader(f"{site_label} Schedule")
    members = list_vps_members(session, site=site)
    if members:
        st.caption(
            ", ".join(
                f"**{m.name}**{' (TL)' if m.is_tl else ''}" for m in members
            )
        )
    else:
        st.warning(f"No members configured for {site_label}.")
        return

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button(f"Generate {site_label} Schedule", type="primary", key=f"gen_{site}"):
            try:
                sched = generate_vps_schedule(session, site, year, month, operator)
                session.commit()
                st.session_state[f"vps_flash_{site}"] = f"Generated {site_label} v{sched.version}"
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    flash = st.session_state.pop(f"vps_flash_{site}", None)
    if flash:
        st.success(flash)

    schedules = list_vps_schedules(session, site, year, month)
    if not schedules:
        st.info(f"No {site_label} schedule for this month yet.")
        return

    version = st.selectbox(
        "Version",
        [s.version for s in schedules],
        index=0,
        key=f"vps_ver_{site}",
    )
    sched = next(s for s in schedules if s.version == version)
    explanation = json.loads(sched.explanation_json or "{}")
    st.markdown(f"**Status:** {sched.status.upper()} · v{sched.version}")

    grid_rows, day_nums, nw_days, day_types = vps_roster_grid(session, sched)
    render_combined_roster(
        grid_rows,
        day_nums,
        nw_days,
        day_types,
        title=f"{site_label} Monthly Roster",
    )
    st.caption(
        "**G** = General (TL on working days) · **1 / 2 / 3** = shift duty (rotates daily) · "
        "**\\*** = carry-over · **X** = off (NW or unassigned) · **NA** = unavailable"
    )

    with st.expander("Schedule notes"):
        st.text(explanation.get("text", ""))

    if sched.status == "draft" and st.button(f"Publish {site_label} Schedule", key=f"pub_{site}"):
        publish_vps_schedule(session, sched.id, operator)
        session.commit()
        st.success("Published.")
        st.rerun()


def render() -> None:
    st.title("VPS Team")

    col1, col2 = st.columns(2)
    with col1:
        year = st.number_input("Year", 2020, 2035, date.today().year, key="vps_year")
    with col2:
        month = st.number_input("Month", 1, 12, date.today().month, key="vps_month")

    with db_session() as session:
        operator = get_operator_name(session)
        tab_dc, tab_dr, tab_members, tab_avail = st.tabs(
            ["DC Schedule", "DR Schedule", "Members", "Availability"]
        )

        with tab_dc:
            _render_site_schedule(session, VPS_SITE_DC, "DC", year, month, operator)

        with tab_dr:
            _render_site_schedule(session, VPS_SITE_DR, "DR", year, month, operator)

        with tab_members:
            st.subheader("VPS Team Members")
            st.caption(
                "Edit names and staff numbers here. Changes apply immediately. "
                "You can also update **`VPS_MEMBER_SEED`** in `database.py` — "
                "matching staff numbers sync on app restart."
            )
            operator_name = current_operator(operator)
            all_members = list_vps_members(session, active_only=False)

            tab_list, tab_add = st.tabs(["Member List", "Add Member"])

            with tab_list:
                if all_members:
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "ID": m.id,
                                    "Name": m.name,
                                    "Staff No.": m.staff_no or "",
                                    "Site": m.site.upper(),
                                    "TL": m.is_tl,
                                    "Sort": m.sort_order,
                                    "Active": m.active,
                                }
                                for m in all_members
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

                    member_options = {
                        f"{m.name} ({m.staff_no}) — {m.site.upper()}": m.id
                        for m in all_members
                    }
                    selected = st.selectbox(
                        "Select member to edit",
                        list(member_options.keys()),
                        key="vps_edit_select",
                    )
                    mid = member_options[selected]
                    member = next(m for m in all_members if m.id == mid)

                    with st.form("vps_edit_member"):
                        new_name = st.text_input("Name", value=member.name)
                        new_staff = st.text_input("Staff No.", value=member.staff_no or "")
                        new_site = st.selectbox(
                            "Site",
                            [VPS_SITE_DC, VPS_SITE_DR],
                            index=0 if member.site == VPS_SITE_DC else 1,
                            format_func=lambda s: s.upper(),
                        )
                        new_tl = st.checkbox(
                            "Team Lead (DC only — General shift on working days)",
                            value=member.is_tl,
                        )
                        new_sort = st.number_input(
                            "Sort order (rotation sequence)",
                            min_value=0,
                            max_value=99,
                            value=member.sort_order,
                        )
                        new_active = st.checkbox("Active", value=member.active)
                        if st.form_submit_button("Save Changes"):
                            try:
                                update_vps_member(
                                    session,
                                    mid,
                                    name=new_name,
                                    staff_no=new_staff,
                                    site=new_site,
                                    is_tl=new_tl if new_site == VPS_SITE_DC else False,
                                    sort_order=int(new_sort),
                                    active=new_active,
                                    operator=operator_name,
                                )
                                session.commit()
                                st.session_state["vps_member_flash"] = f"Updated {new_name.strip()}"
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))

                    if st.button("Deactivate Member", key="vps_deactivate"):
                        try:
                            deactivate_vps_member(session, mid, operator_name)
                            session.commit()
                            st.session_state["vps_member_flash"] = f"Deactivated {member.name}"
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                else:
                    st.info("No VPS members in database.")

            with tab_add:
                with st.form("vps_add_member"):
                    name = st.text_input("Name")
                    staff_no = st.text_input("Staff No.")
                    site = st.selectbox(
                        "Site",
                        [VPS_SITE_DC, VPS_SITE_DR],
                        format_func=lambda s: s.upper(),
                    )
                    is_tl = st.checkbox("Team Lead (DC site only)")
                    sort_order = st.number_input("Sort order", min_value=0, max_value=99, value=1)
                    if st.form_submit_button("Add Member"):
                        if not name.strip() or not staff_no.strip():
                            st.error("Name and Staff No. are required.")
                        else:
                            try:
                                add_vps_member(
                                    session,
                                    name,
                                    staff_no,
                                    site,
                                    is_tl=is_tl if site == VPS_SITE_DC else False,
                                    sort_order=int(sort_order),
                                    operator=operator_name,
                                )
                                session.commit()
                                st.session_state["vps_member_flash"] = f"Added {name.strip()}"
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))

            if st.session_state.get("vps_member_flash"):
                st.success(st.session_state.pop("vps_member_flash"))

        with tab_avail:
            st.subheader("VPS Availability")
            members = list_vps_members(session, active_only=True)
            if not members:
                st.info("No VPS members.")
                return
            member_map = {f"{m.name} ({m.staff_no}) [{m.site.upper()}]": m.id for m in members}

            tab_add, tab_list = st.tabs(["Add", "Records"])
            with tab_add:
                with st.form("vps_add_avail"):
                    pick = st.selectbox("Member", list(member_map.keys()))
                    scope = st.radio("Scope", ["Single Date", "Date Range", "Entire Month"])
                    c1, c2 = st.columns(2)
                    with c1:
                        start = st.date_input("From", value=date.today())
                    with c2:
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
                        add_vps_availability(
                            session,
                            member_map[pick],
                            start,
                            end,
                            status,
                            reason,
                            operator,
                        )
                        st.success("Saved. Regenerate VPS schedules to apply.")
                        st.rerun()

            with tab_list:
                records = list_vps_availability(session)
                if records:
                    rows = []
                    for r in records:
                        m = next((x for x in members if x.id == r.member_id), None)
                        rows.append(
                            {
                                "ID": r.id,
                                "Member": m.name if m else r.member_id,
                                "Site": m.site.upper() if m else "",
                                "From": r.start_date,
                                "To": r.end_date,
                                "Status": r.status,
                                "Reason": r.reason or "",
                            }
                        )
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                    del_id = st.number_input("Delete record ID", min_value=0, step=1, key="vps_del")
                    if st.button("Delete Record") and del_id > 0:
                        delete_vps_availability(session, int(del_id), operator)
                        st.rerun()
                else:
                    st.info("No VPS availability records.")
