"""Per-employee availability PIN verification."""

from __future__ import annotations

from sqlalchemy.orm import Session

from config import (
    ROLE_NON_EXECUTIVE,
    ROLE_NON_EXECUTIVE_BACKUP,
    ROLE_PROJECT_ENGINEER,
    ROLE_TRAINEE_ENGINEER,
)
from services.auth_service import verify_password
from services.employee_service import get_employee

PIN_ROLES = frozenset(
    {
        ROLE_NON_EXECUTIVE,
        ROLE_NON_EXECUTIVE_BACKUP,
        ROLE_TRAINEE_ENGINEER,
        ROLE_PROJECT_ENGINEER,
    }
)


def employee_requires_avail_pin(role_code: str) -> bool:
    return role_code in PIN_ROLES


def verify_employee_availability_pin(session: Session, employee_id: int, code: str) -> bool:
    emp = get_employee(session, employee_id)
    if not emp or not emp.availability_pin_hash:
        return False
    return verify_password(code.strip(), emp.availability_pin_hash)
