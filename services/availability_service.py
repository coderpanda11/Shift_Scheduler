"""Availability management service."""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from config import BLOCKING_STATUSES
from models import AuditLog, Availability, Employee
from scheduler.calendar_util import dates_in_range, month_dates


def list_availability(session: Session, employee_id: int | None = None) -> list[Availability]:
    q = select(Availability).order_by(Availability.start_date.desc())
    if employee_id:
        q = q.where(Availability.employee_id == employee_id)
    return list(session.scalars(q).all())


def add_availability(
    session: Session,
    employee_id: int,
    start_date: date,
    end_date: date,
    status: str,
    reason: str | None = None,
    operator: str = "DC/In-Charge",
) -> Availability:
    if start_date > end_date:
        raise ValueError("Start date must be on or before end date")
    rec = Availability(
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        status=status.lower(),
        reason=reason,
    )
    session.add(rec)
    session.flush()
    emp = session.get(Employee, employee_id)
    session.add(
        AuditLog(
            action="availability_changed",
            entity_type="availability",
            entity_id=rec.id,
            new_value=f"{emp.name if emp else employee_id}: {status} {start_date} to {end_date}",
            reason=reason,
            created_by=operator,
        )
    )
    return rec


def delete_availability(session: Session, availability_id: int, operator: str = "DC/In-Charge") -> None:
    rec = session.get(Availability, availability_id)
    if rec:
        session.add(
            AuditLog(
                action="availability_deleted",
                entity_type="availability",
                entity_id=availability_id,
                old_value=str(rec.id),
                created_by=operator,
            )
        )
        session.delete(rec)


def build_availability_map(
    session: Session, year: int, month: int
) -> dict[int, set[date]]:
    """Build employee_id -> set of blocked dates for a month."""
    month_day_set = set(month_dates(year, month))
    records = list(session.scalars(select(Availability)).all())
    result: dict[int, set[date]] = {}
    for rec in records:
        if rec.status == "available":
            continue
        if rec.status not in BLOCKING_STATUSES and rec.status != "unavailable":
            # treat unknown blocking statuses as blocking
            pass
        for d in dates_in_range(rec.start_date, rec.end_date):
            if d in month_day_set:
                result.setdefault(rec.employee_id, set()).add(d)
    return result


def count_unavailable_in_month(session: Session, year: int, month: int) -> int:
    """Count distinct employees with any blocking availability in month."""
    amap = build_availability_map(session, year, month)
    return len(amap)


def availability_affects_schedules(session: Session, year: int, month: int) -> bool:
    """True if any blocking availability exists for the month."""
    return count_unavailable_in_month(session, year, month) > 0
