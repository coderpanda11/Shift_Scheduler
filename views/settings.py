"""Settings page."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from models import AuditLog, ShiftType
from services.auth_service import create_user, delete_user, list_users, reset_password
from services.employee_service import list_employees
from services.settings_service import (
    get_operator_name,
    get_saturday_rule,
    get_scheduling_rules,
    get_score_weights,
    get_weekend_days,
    set_operator_name,
    set_scheduling_rules,
    set_score_weights,
    set_weekend_days,
)
from utils.auth_context import current_operator, is_admin
from utils.session import db_session

DAY_OPTIONS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def render() -> None:
    st.title("Settings")

    with db_session() as session:
        tabs = ["General", "Scheduling Rules", "Shift Types", "Audit Log"]
        if is_admin():
            tabs.append("Login Users")
        tab_objects = st.tabs(tabs)
        tab_gen, tab_rules, tab_shifts, tab_audit = tab_objects[:4]
        tab_users = tab_objects[4] if is_admin() else None

        with tab_gen:
            operator = st.text_input("Operator Name (reports)", value=get_operator_name(session))
            st.info(
                "**Working calendar:** Sunday off · **1st & 3rd Saturday** holiday · "
                "2nd / 4th / 5th Saturday working. Manual holidays & overrides still apply."
            )
            st.caption(
                "Staff availability PINs are **per employee** — reset under "
                "**Employees → Edit → Reset availability PIN**."
            )
            st.caption(f"Saturday rule setting: `{get_saturday_rule(session)}`")
            weekends = get_weekend_days(session)
            selected_days = st.multiselect(
                "Always-off weekdays (default: Sunday only)",
                DAY_OPTIONS,
                default=[DAY_OPTIONS[d] for d in weekends if d < len(DAY_OPTIONS)],
            )
            if st.button("Save General Settings", key="save_gen"):
                set_operator_name(session, operator)
                set_weekend_days(session, [DAY_OPTIONS.index(d) for d in selected_days])
                session.commit()
                st.success("Saved.")

        with tab_rules:
            rules = get_scheduling_rules(session)
            weights = get_score_weights(session)
            st.subheader("Scheduling Rules")
            updated_rules = {}
            for key, val in rules.items():
                if isinstance(val, bool):
                    updated_rules[key] = st.checkbox(key, value=val, key=f"rule_{key}")
                elif isinstance(val, int):
                    updated_rules[key] = st.number_input(key, value=val, key=f"rule_{key}")
                else:
                    updated_rules[key] = val
            st.subheader("Score Weights")
            updated_weights = {}
            for key, val in weights.items():
                updated_weights[key] = st.number_input(key, value=float(val), key=f"w_{key}")
            if st.button("Save Rules & Weights", key="save_rules"):
                set_scheduling_rules(session, updated_rules)
                set_score_weights(session, updated_weights)
                session.commit()
                st.success("Saved.")

        with tab_shifts:
            shifts = list(session.scalars(select(ShiftType).order_by(ShiftType.number)).all())
            for s in shifts:
                st.markdown(f"**Shift {s.number}:** {s.name} ({s.start_time} – {s.end_time})")
            st.caption("Shift timings are display-only; scheduling uses shift numbers 1/2/3.")

        with tab_audit:
            logs = list(session.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100)).all())
            if logs:
                rows = [
                    {
                        "Time": l.timestamp.strftime("%Y-%m-%d %H:%M"),
                        "Action": l.action,
                        "Entity": l.entity_type,
                        "Old": l.old_value,
                        "New": l.new_value,
                        "Reason": l.reason,
                        "By": l.created_by,
                    }
                    for l in logs
                ]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info("No audit entries yet.")

        if tab_users is not None:
            with tab_users:
                st.subheader("Login Users")
                users = list_users(session)
                employees = list_employees(session, active_only=False)
                emp_names = {e.id: e.name for e in employees}
                if users:
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "ID": u.id,
                                    "Username": u.username,
                                    "Display Name": u.display_name,
                                    "Role": u.role,
                                    "Employee": emp_names.get(u.employee_id, "") if u.employee_id else "",
                                    "Active": u.active,
                                }
                                for u in users
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                with st.form("add_user_form"):
                    st.markdown("**Add login user**")
                    nu = st.text_input("Login ID / Username")
                    npw = st.text_input("Password", type="password")
                    ndn = st.text_input("Display Name")
                    nr = st.selectbox("Role", ["admin", "dc_incharge", "staff"])
                    link_emp = None
                    if nr == "staff":
                        emp_opts = {f"{e.name} ({e.staff_no})": e.id for e in employees}
                        if emp_opts:
                            pick = st.selectbox("Link to employee", list(emp_opts.keys()))
                            link_emp = emp_opts[pick]
                        else:
                            st.caption("Add employees first to link staff logins.")
                    if st.form_submit_button("Create User"):
                        try:
                            create_user(
                                session,
                                nu,
                                npw,
                                ndn,
                                nr,
                                employee_id=link_emp,
                                operator=current_operator(),
                            )
                            session.commit()
                            st.success(f"Created user {nu}")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                del_id = st.number_input("Delete user ID", min_value=0, step=1, key="del_user_id")
                if st.button("Delete User") and del_id > 0:
                    try:
                        delete_user(session, int(del_id), current_operator())
                        session.commit()
                        st.success("User deleted.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
