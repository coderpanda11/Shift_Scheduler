"""Employee management service."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import default_availability_pin
from models import AuditLog, Availability, Employee, Role, ShiftAssignment
from services.auth_service import hash_password


def list_roles(session: Session) -> list[Role]:
    return list(session.scalars(select(Role).order_by(Role.sort_order)).all())


def list_employees(session: Session, active_only: bool = False) -> list[Employee]:
    q = select(Employee).join(Role).order_by(Role.sort_order, Employee.name)
    if active_only:
        q = q.where(Employee.active.is_(True))
    return list(session.scalars(q).all())


def get_employee(session: Session, employee_id: int) -> Optional[Employee]:
    return session.get(Employee, employee_id)


def add_employee(
    session: Session,
    name: str,
    role_id: int,
    staff_no: str | None = None,
    notes: str | None = None,
    operator: str = "DC/In-Charge",
) -> Employee:
    staff = staff_no.strip() if staff_no else None
    if staff:
        existing = session.scalar(select(Employee).where(Employee.staff_no == staff))
        if existing:
            raise ValueError(f"Staff no. {staff} is already assigned to {existing.name}")
    emp = Employee(
        name=name.strip(),
        role_id=role_id,
        staff_no=staff,
        active=True,
        notes=notes,
    )
    session.add(emp)
    session.flush()
    if staff:
        emp.availability_pin_hash = hash_password(default_availability_pin(staff))
    session.add(
        AuditLog(
            action="employee_added",
            entity_type="employee",
            entity_id=emp.id,
            new_value=f"{name} ({staff or 'no staff no.'})",
            created_by=operator,
        )
    )
    return emp


def set_employee_availability_pin(
    session: Session,
    employee_id: int,
    pin: str,
    operator: str = "DC/In-Charge",
) -> Employee:
    emp = session.get(Employee, employee_id)
    if not emp:
        raise ValueError(f"Employee {employee_id} not found")
    pin = pin.strip()
    if not pin:
        raise ValueError("Availability PIN cannot be empty")
    emp.availability_pin_hash = hash_password(pin)
    emp.updated_at = datetime.utcnow()
    session.add(
        AuditLog(
            action="employee_avail_pin_reset",
            entity_type="employee",
            entity_id=emp.id,
            new_value=emp.staff_no or emp.name,
            created_by=operator,
        )
    )
    return emp


def update_employee(
    session: Session,
    employee_id: int,
    name: str | None = None,
    role_id: int | None = None,
    active: bool | None = None,
    staff_no: str | None = None,
    notes: str | None = None,
    operator: str = "DC/In-Charge",
) -> Employee:
    emp = session.get(Employee, employee_id)
    if not emp:
        raise ValueError(f"Employee {employee_id} not found")
    old = f"{emp.name} / {emp.staff_no or ''}"
    if name is not None:
        emp.name = name.strip()
    if role_id is not None:
        emp.role_id = role_id
    if active is not None:
        emp.active = active
    if staff_no is not None:
        staff = staff_no.strip() or None
        if staff:
            clash = session.scalar(
                select(Employee).where(Employee.staff_no == staff, Employee.id != employee_id)
            )
            if clash:
                raise ValueError(f"Staff no. {staff} is already assigned to {clash.name}")
        emp.staff_no = staff
    if notes is not None:
        emp.notes = notes
    emp.updated_at = datetime.utcnow()
    session.add(
        AuditLog(
            action="employee_updated",
            entity_type="employee",
            entity_id=emp.id,
            old_value=old,
            new_value=f"{emp.name} / {emp.staff_no or ''}",
            created_by=operator,
        )
    )
    return emp


def deactivate_employee(
    session: Session, employee_id: int, operator: str = "DC/In-Charge"
) -> Employee:
    return update_employee(session, employee_id, active=False, operator=operator)


def delete_employee(
    session: Session,
    employee_id: int,
    operator: str = "DC/In-Charge",
) -> None:
    """Delete employee if not referenced in any schedule assignment."""
    emp = session.get(Employee, employee_id)
    if not emp:
        raise ValueError(f"Employee {employee_id} not found")

    assign_count = session.scalar(
        select(func.count())
        .select_from(ShiftAssignment)
        .where(ShiftAssignment.employee_id == employee_id)
    )
    if assign_count and assign_count > 0:
        raise ValueError(
            f"Cannot delete {emp.name}: used in {assign_count} schedule assignment(s). "
            "Deactivate instead — past rosters keep their name snapshot."
        )

    for av in session.scalars(select(Availability).where(Availability.employee_id == employee_id)):
        session.delete(av)

    session.add(
        AuditLog(
            action="employee_deleted",
            entity_type="employee",
            entity_id=emp.id,
            old_value=f"{emp.name} / {emp.staff_no or ''}",
            created_by=operator,
        )
    )
    session.delete(emp)


def employees_by_role_code(session: Session, active_only: bool = True) -> dict[str, list[Employee]]:
    """Group active employees by role code."""
    emps = list_employees(session, active_only=active_only)
    out: dict[str, list[Employee]] = {}
    for e in emps:
        code = e.role.code
        out.setdefault(code, []).append(e)
    return out
