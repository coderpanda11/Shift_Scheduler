"""Shift Scheduler — Streamlit entry point."""

from __future__ import annotations

import streamlit as st

from database import init_db
from views import (
    availability,
    current_schedule,
    dashboard,
    duty_statistics,
    employees,
    generate_schedule,
    login,
    schedule_history,
    settings,
    staff_availability,
    staff_schedule,
    vps_team,
    working_calendar,
)
from views.layout import inject_global_css, render_app_header
from utils.permissions import NAV_ICONS, pages_for_role

st.set_page_config(
    page_title="Duty Roster Management System",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
inject_global_css()

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if not st.session_state.auth_user:
    login.render()
    st.stop()

user = st.session_state.auth_user
role = user.get("role", "")

ALL_RENDERERS = {
    "Dashboard": dashboard.render,
    "Generate Schedule": generate_schedule.render,
    "Employees": employees.render,
    "Availability": availability.render,
    "Working Calendar": working_calendar.render,
    "Current Schedule": current_schedule.render,
    "Duty Statistics": duty_statistics.render,
    "Schedule History": schedule_history.render,
    "Settings": settings.render,
    "VPS Team": vps_team.render,
    "Team Schedule": staff_schedule.render,
    "My Availability": staff_availability.render,
}

allowed = pages_for_role(role)
PAGES = {k: ALL_RENDERERS[k] for k in allowed}

nav_labels = [f"{NAV_ICONS.get(k, '📄')} {k}" for k in PAGES]
label_to_key = {label: key for label, key in zip(nav_labels, PAGES.keys())}

st.sidebar.markdown(f"**Signed in as**  \n{user['display_name']}")
st.sidebar.caption(f"Login: {user['username']} · {role.replace('_', ' ').title()}")
if st.sidebar.button("Logout", key="logout_btn"):
    st.session_state.auth_user = None
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("**Navigation**")
choice = st.sidebar.radio(
    "Navigation",
    nav_labels,
    key="main_nav",
    label_visibility="collapsed",
)
page_key = label_to_key[choice]

render_app_header()
PAGES[page_key]()
