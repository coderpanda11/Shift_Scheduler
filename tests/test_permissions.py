"""Role-based page access tests."""

from utils.permissions import MANAGER_PAGES, STAFF_PAGES, pages_for_role


def test_staff_pages():
    assert pages_for_role("staff") == STAFF_PAGES
    assert "Dashboard" not in pages_for_role("staff")
    assert "Team Schedule" in pages_for_role("staff")
    assert "My Availability" in pages_for_role("staff")


def test_manager_pages():
    for role in ("admin", "dc_incharge"):
        assert pages_for_role(role) == MANAGER_PAGES
        assert "Team Schedule" not in pages_for_role(role)
