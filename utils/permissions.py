"""Role-based page access."""

from __future__ import annotations

MANAGER_PAGES = [
    "Dashboard",
    "Generate Schedule",
    "VPS Team",
    "Employees",
    "Availability",
    "Working Calendar",
    "Current Schedule",
    "Duty Statistics",
    "Schedule History",
    "Settings",
    
]

STAFF_PAGES = [
    "Team Schedule",
    "My Availability",
]

NAV_ICONS = {
    "Dashboard": "🏠",
    "Generate Schedule": "📅",
    "Employees": "👥",
    "Availability": "🚫",
    "Working Calendar": "🗓",
    "Current Schedule": "📋",
    "Duty Statistics": "📊",
    "Schedule History": "🕘",
    "Settings": "⚙️",
    "VPS Team": "🖥",
    "Team Schedule": "📋",
    "My Availability": "🚫",
}


def pages_for_role(role: str) -> list[str]:
    if role == "staff":
        return list(STAFF_PAGES)
    return list(MANAGER_PAGES)
