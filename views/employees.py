"""Employee management page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services.employee_service import (
    add_employee,
    deactivate_employee,
    delete_employee,
    list_employees,
    list_roles,
    update_employee,
)
from services.schedule_service import employee_duty_history
from services.settings_service import get_operator_name
from utils.auth_context import current_operator
from utils.session import db_session


def render() -> None:
    st.title("Employee Management")

    with db_session() as session:
        operator = current_operator(get_operator_name(session))
        roles = list_roles(session)
        role_names = [r.name for r in roles]
        role_map = {r.name: r.id for r in roles}
        employees = list_employees(session)
        emp_options = {
            f"{e.name} ({e.staff_no or '—'}) — {e.role.name}": e.id for e in employees
        }

        tab_list, tab_add, tab_history = st.tabs(["Employees", "Add Employee", "Duty History"])

        with tab_list:
            if employees:
                rows = [
                    {
                        "ID": e.id,
                        "SAP ID / Staff No.": e.staff_no or "",
                        "Name": e.name,
                        "Role": e.role.name,
                        "Active": e.active,
                        "Notes": e.notes or "",
                    }
                    for e in employees
                ]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            st.subheader("Edit / Deactivate / Delete")
            if emp_options:
                selected = st.selectbox(
                    "Select employee",
                    list(emp_options.keys()),
                    key="emp_edit_select",
                )
                emp_id = emp_options[selected]
                emp = next(e for e in employees if e.id == emp_id)
                role_index = role_names.index(emp.role.name) if emp.role.name in role_names else 0

                with st.form("edit_emp_form", clear_on_submit=False):
                    staff_no = st.text_input(
                        "SAP ID / Staff No.",
                        value=emp.staff_no or "",
                        key="emp_edit_staff",
                    )
                    new_name = st.text_input("Name", value=emp.name, key="emp_edit_name")
                    new_role = st.selectbox(
                        "Role",
                        role_names,
                        index=role_index,
                        key="emp_edit_role",
                    )
                    active = st.checkbox("Active", value=emp.active, key="emp_edit_active")
                    notes = st.text_area("Notes", value=emp.notes or "", key="emp_edit_notes")
                    if st.form_submit_button("Save Changes"):
                        try:
                            update_employee(
                                session,
                                emp_id,
                                name=new_name,
                                role_id=role_map[new_role],
                                active=active,
                                staff_no=staff_no,
                                notes=notes,
                                operator=operator,
                            )
                            session.commit()
                            st.session_state["emp_flash"] = f"Updated {new_name.strip()}"
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Update failed: {exc}")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Deactivate Employee", type="secondary", key="emp_deactivate"):
                        try:
                            deactivate_employee(session, emp_id, operator=operator)
                            session.commit()
                            st.session_state["emp_flash"] = f"Deactivated {emp.name}"
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Deactivate failed: {exc}")

                with col2:
                    st.markdown("**Delete permanently**")
                    confirm_delete = st.checkbox(
                        f"I confirm delete of {emp.name}",
                        key="emp_delete_confirm",
                    )
                    if st.button("Delete Employee", type="primary", key="emp_delete"):
                        if not confirm_delete:
                            st.warning("Tick the confirmation box to delete.")
                        else:
                            try:
                                delete_employee(session, emp_id, operator=operator)
                                session.commit()
                                st.session_state["emp_flash"] = f"Deleted {emp.name}"
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))

        if st.session_state.get("emp_flash"):
            st.success(st.session_state.pop("emp_flash"))

        with tab_add:
            with st.form("add_emp_form"):
                staff_no = st.text_input("SAP ID / Staff No.", key="emp_add_staff")
                name = st.text_input("Name", key="emp_add_name")
                role = st.selectbox("Role", role_names, key="emp_add_role")
                notes = st.text_area("Notes", key="emp_add_notes")
                if st.form_submit_button("Add Employee"):
                    if not name.strip():
                        st.error("Name is required.")
                    elif not staff_no.strip():
                        st.error("SAP ID / Staff No. is required.")
                    else:
                        try:
                            add_employee(
                                session,
                                name,
                                role_map[role],
                                staff_no=staff_no,
                                notes=notes,
                                operator=operator,
                            )
                            session.commit()
                            st.session_state["emp_flash"] = f"Added {name.strip()}"
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Add failed: {exc}")

        with tab_history:
            if emp_options:
                hist_emp = st.selectbox(
                    "Employee for history",
                    list(emp_options.keys()),
                    key="emp_hist_select",
                )
                history = employee_duty_history(session, emp_options[hist_emp])
                if history:
                    for h in history:
                        st.markdown(
                            f"**{h['month']:02d}/{h['year']}** (v{h['version']}, {h['status']}) — "
                            f"1st: {h['shifts'][1]}, 2nd: {h['shifts'][2]}, 3rd: {h['shifts'][3]}, Total: {h['total']}"
                        )
                else:
                    st.info("No schedule history for this employee.")
