"""Working calendar and holiday service."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AuditLog, DateOverride, Holiday
from scheduler.calendar_util import classify_month, count_working_non_working, expand_holidays_for_month


def list_holidays(session: Session) -> list[Holiday]:
    return list(session.scalars(select(Holiday).order_by(Holiday.date)).all())


def add_holiday(
    session: Session,
    holiday_date: date,
    name: str,
    repeats_yearly: bool = False,
    operator: str = "DC/In-Charge",
) -> Holiday:
    h = Holiday(date=holiday_date, name=name, repeats_yearly=repeats_yearly)
    session.add(h)
    session.flush()
    session.add(
        AuditLog(
            action="holiday_added",
            entity_type="holiday",
            entity_id=h.id,
            new_value=f"{name} on {holiday_date}",
            created_by=operator,
        )
    )
    return h


def delete_holiday(session: Session, holiday_id: int, operator: str = "DC/In-Charge") -> None:
    h = session.get(Holiday, holiday_id)
    if h:
        session.add(
            AuditLog(
                action="holiday_deleted",
                entity_type="holiday",
                entity_id=holiday_id,
                old_value=h.name,
                created_by=operator,
            )
        )
        session.delete(h)


def list_date_overrides(session: Session) -> list[DateOverride]:
    return list(session.scalars(select(DateOverride).order_by(DateOverride.date)).all())


def set_date_override(
    session: Session,
    override_date: date,
    is_working: bool,
    reason: str | None = None,
    operator: str = "DC/In-Charge",
) -> DateOverride:
    existing = session.scalar(
        select(DateOverride).where(DateOverride.date == override_date)
    )
    if existing:
        existing.is_working = is_working
        existing.reason = reason
        rec = existing
    else:
        rec = DateOverride(date=override_date, is_working=is_working, reason=reason)
        session.add(rec)
    session.flush()
    session.add(
        AuditLog(
            action="date_override_set",
            entity_type="date_override",
            entity_id=rec.id,
            new_value=f"{override_date}: {'W' if is_working else 'NW'}",
            reason=reason,
            created_by=operator,
        )
    )
    return rec


def remove_date_override(session: Session, override_date: date) -> None:
    rec = session.scalar(select(DateOverride).where(DateOverride.date == override_date))
    if rec:
        session.delete(rec)


def get_calendar_for_month(
    session: Session,
    year: int,
    month: int,
) -> list:
    """Return classified days for a month."""
    from services.settings_service import get_calendar_settings

    weekend_days, saturday_rule = get_calendar_settings(session)
    holidays = [(h.date, h.repeats_yearly) for h in list_holidays(session)]
    holiday_dates = expand_holidays_for_month(year, month, holidays)
    overrides = {o.date: o.is_working for o in list_date_overrides(session)}
    return classify_month(
        year, month, weekend_days, holiday_dates, overrides, saturday_rule
    )


def calendar_summary(session: Session, year: int, month: int) -> dict:
    days = get_calendar_for_month(session, year, month)
    w, nw = count_working_non_working(days)
    return {"working_days": w, "non_working_days": nw, "total_days": len(days), "days": days}
