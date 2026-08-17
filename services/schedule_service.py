"""Schedule generation, versioning, manual override, and publish."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from config import ROLE_NON_EXECUTIVE, ROLE_NON_EXECUTIVE_BACKUP, ROLE_TRAINEE_ENGINEER
from models import AuditLog, Employee, Holiday, ManualOverride, Schedule, ShiftAssignment
from scheduler.engine import ScheduleContext, ScheduleEngine, ScheduleResult
from scheduler.fairness import EmployeeInfo
from scheduler.validator import Assignment, validate_schedule
from services.availability_service import build_availability_map
from services.calendar_service import list_date_overrides, list_holidays
from services.employee_service import list_employees
from services.settings_service import (
    get_calendar_settings,
    get_operator_name,
    get_scheduling_rules,
    get_score_weights,
)


def _employees_to_info(session: Session) -> list[EmployeeInfo]:
    emps = list_employees(session, active_only=True)
    return [
        EmployeeInfo(id=e.id, name=e.name, role_code=e.role.code, active=e.active)
        for e in emps
    ]


def _prior_month_stats(session: Session, year: int, month: int) -> dict[int, dict] | None:
    """Load stats from last published schedule for cross-month fairness."""
    if month == 1:
        py, pm = year - 1, 12
    else:
        py, pm = year, month - 1
    sched = session.scalar(
        select(Schedule)
        .where(
            Schedule.year == py,
            Schedule.month == pm,
            Schedule.status == "published",
        )
        .order_by(Schedule.version.desc())
        .limit(1)
    )
    if not sched:
        return None
    stats: dict[int, dict] = {}
    for a in sched.assignments:
        if a.employee_id not in stats:
            stats[a.employee_id] = {"shift_counts": {1: 0, 2: 0, 3: 0}, "total": 0}
        stats[a.employee_id]["shift_counts"][a.shift_number] = (
            stats[a.employee_id]["shift_counts"].get(a.shift_number, 0) + 1
        )
        stats[a.employee_id]["total"] += 1
    return stats


def build_context(session: Session, year: int, month: int) -> ScheduleContext:
    rules = get_scheduling_rules(session)
    weights = get_score_weights(session)
    prior = _prior_month_stats(session, year, month) if rules.get("cross_month_fairness") else None
    holidays = [(h.date, h.repeats_yearly) for h in list_holidays(session)]
    overrides = {o.date: o.is_working for o in list_date_overrides(session)}
    weekend_days, saturday_rule = get_calendar_settings(session)
    return ScheduleContext(
        year=year,
        month=month,
        employees=_employees_to_info(session),
        availability_map=build_availability_map(session, year, month),
        weekend_days=weekend_days,
        saturday_rule=saturday_rule,
        holidays=holidays,
        date_overrides=overrides,
        rules=rules,
        weights=weights,
        prior_month_stats=prior,
    )


def preflight_check(session: Session, year: int, month: int) -> dict:
    """Pre-generation summary."""
    by_role = {}
    for e in list_employees(session, active_only=True):
        by_role.setdefault(e.role.code, []).append(e)

    primary = by_role.get(ROLE_NON_EXECUTIVE, [])
    backup = by_role.get(ROLE_NON_EXECUTIVE_BACKUP, [])
    trainees = by_role.get(ROLE_TRAINEE_ENGINEER, [])

    amap = build_availability_map(session, year, month)
    month_days = set()
    from scheduler.calendar_util import month_dates

    month_days = set(month_dates(year, month))
    all_primary_avail = all(
        not (amap.get(e.id, set()) & month_days) for e in primary
    )
    backup_avail = (
        all(not (amap.get(e.id, set()) & month_days) for e in backup) if backup else False
    )

    mode = "ideal" if all_primary_avail else "backup_rebalanced"

    return {
        "primary_count": len(primary),
        "primary_all_available": all_primary_avail,
        "backup_available": backup_avail if backup else False,
        "trainee_count": len(trainees),
        "mode": mode,
        "primary_names": [e.name for e in primary],
        "backup_names": [e.name for e in backup],
    }


def next_version(session: Session, year: int, month: int) -> int:
    max_v = session.scalar(
        select(func.max(Schedule.version)).where(
            Schedule.year == year, Schedule.month == month
        )
    )
    return (max_v or 0) + 1


def generate_schedule(
    session: Session,
    year: int,
    month: int,
    operator: str | None = None,
) -> Schedule:
    """Generate and persist a new schedule version."""
    operator = operator or get_operator_name(session)
    ctx = build_context(session, year, month)
    engine = ScheduleEngine()
    result = engine.generate_schedule(ctx)
    version = next_version(session, year, month)

    sched = Schedule(
        month=month,
        year=year,
        version=version,
        status="draft",
        scheduling_mode=result.mode,
        explanation_json=json.dumps(result.explanation),
        validation_json=json.dumps(
            {
                "quality": result.validation.quality if result.validation else "good",
                "conflicts": result.validation.conflicts if result.validation else [],
                "warnings": result.validation.warnings if result.validation else [],
            }
        ),
        quality=result.validation.quality if result.validation else "good",
        created_by=operator,
    )
    session.add(sched)
    session.flush()

    for a in result.assignments:
        session.add(
            ShiftAssignment(
                schedule_id=sched.id,
                date=a.date,
                shift_number=a.shift_number,
                slot_kind=a.slot_kind,
                employee_id=a.employee_id,
                employee_name_snapshot=a.employee_name,
                role_snapshot=a.role_code,
                is_manual_override=False,
            )
        )

    session.add(
        AuditLog(
            action="schedule_generated",
            entity_type="schedule",
            entity_id=sched.id,
            new_value=f"{year}-{month:02d} v{version} mode={result.mode}",
            created_by=operator,
        )
    )
    return sched


def get_schedule(session: Session, schedule_id: int) -> Optional[Schedule]:
    return session.get(Schedule, schedule_id)


def list_schedules(
    session: Session,
    year: int | None = None,
    month: int | None = None,
    status: str | None = None,
) -> list[Schedule]:
    q = select(Schedule).order_by(Schedule.year.desc(), Schedule.month.desc(), Schedule.version.desc())
    if year:
        q = q.where(Schedule.year == year)
    if month:
        q = q.where(Schedule.month == month)
    if status:
        q = q.where(Schedule.status == status)
    return list(session.scalars(q).all())


def get_latest_schedule(
    session: Session, year: int, month: int, status: str | None = None
) -> Optional[Schedule]:
    q = select(Schedule).where(Schedule.year == year, Schedule.month == month)
    if status:
        q = q.where(Schedule.status == status)
    q = q.order_by(Schedule.version.desc()).limit(1)
    return session.scalar(q)


def publish_schedule(session: Session, schedule_id: int, operator: str | None = None) -> Schedule:
    operator = operator or get_operator_name(session)
    sched = session.get(Schedule, schedule_id)
    if not sched:
        raise ValueError("Schedule not found")
    validation = json.loads(sched.validation_json or "{}")
    if validation.get("quality") == "conflict":
        raise ValueError("Cannot publish schedule with conflicts")
    sched.status = "published"
    sched.published_at = datetime.utcnow()
    session.add(
        AuditLog(
            action="schedule_published",
            entity_type="schedule",
            entity_id=sched.id,
            new_value=f"v{sched.version}",
            created_by=operator,
        )
    )
    return sched


def archive_schedule(session: Session, schedule_id: int, operator: str | None = None) -> Schedule:
    sched = session.get(Schedule, schedule_id)
    if sched:
        sched.status = "archived"
        session.add(
            AuditLog(
                action="schedule_archived",
                entity_type="schedule",
                entity_id=sched.id,
                created_by=operator or get_operator_name(session),
            )
        )
    return sched


def assignments_to_list(sched: Schedule) -> list[Assignment]:
    return [
        Assignment(
            date=a.date,
            shift_number=a.shift_number,
            slot_kind=a.slot_kind,
            employee_id=a.employee_id,
            employee_name=a.employee_name_snapshot,
            role_code=a.role_snapshot,
            is_working_day=True,  # filled from calendar when needed
        )
        for a in sched.assignments
    ]


def manual_override_assignment(
    session: Session,
    schedule_id: int,
    assignment_id: int,
    new_employee_id: int,
    reason: str | None,
    confirm_warnings: bool,
    operator: str | None = None,
) -> tuple[ShiftAssignment, list[str], list[str]]:
    """Replace an assignment with validation."""
    operator = operator or get_operator_name(session)
    assignment = session.get(ShiftAssignment, assignment_id)
    if not assignment or assignment.schedule_id != schedule_id:
        raise ValueError("Assignment not found")

    sched = session.get(Schedule, schedule_id)
    new_emp = session.get(Employee, new_employee_id)
    if not new_emp or not new_emp.active:
        raise ValueError("New employee not found or inactive")

    errors: list[str] = []
    warnings: list[str] = []

    # Availability
    amap = build_availability_map(session, sched.year, sched.month)
    if assignment.date in amap.get(new_employee_id, set()):
        errors.append(f"{new_emp.name} is unavailable on {assignment.date}")

    # Double shift
    same_day = [
        a
        for a in sched.assignments
        if a.date == assignment.date and a.employee_id == new_employee_id and a.id != assignment_id
    ]
    if same_day:
        errors.append(f"{new_emp.name} already has a shift on {assignment.date}")

    # Role: trainee on 3rd
    if assignment.shift_number == 3 and new_emp.role.code == "TRAINEE_ENGINEER":
        errors.append("Trainees cannot work 3rd shift")

    if errors:
        return assignment, errors, warnings

    if warnings and not confirm_warnings:
        return assignment, errors, warnings

    old_id = assignment.employee_id
    old_name = assignment.employee_name_snapshot
    assignment.employee_id = new_emp.id
    assignment.employee_name_snapshot = new_emp.name
    assignment.role_snapshot = new_emp.role.code
    assignment.is_manual_override = True

    session.add(
        ManualOverride(
            schedule_id=schedule_id,
            assignment_id=assignment_id,
            old_employee_id=old_id,
            new_employee_id=new_employee_id,
            reason=reason,
            warnings_confirmed=confirm_warnings,
            created_by=operator,
        )
    )
    session.add(
        AuditLog(
            action="manual_override",
            entity_type="assignment",
            entity_id=assignment_id,
            old_value=old_name,
            new_value=new_emp.name,
            reason=reason,
            created_by=operator,
        )
    )
    return assignment, errors, warnings


def employee_duty_history(session: Session, employee_id: int) -> list[dict]:
    """Per-month duty counts from published/archived schedule snapshots."""
    schedules = list_schedules(session)
    history: list[dict] = []
    for sched in schedules:
        if sched.status not in ("published", "archived", "draft"):
            continue
        assigns = [a for a in sched.assignments if a.employee_id == employee_id]
        if not assigns:
            continue
        counts = {1: 0, 2: 0, 3: 0}
        for a in assigns:
            counts[a.shift_number] = counts.get(a.shift_number, 0) + 1
        history.append(
            {
                "year": sched.year,
                "month": sched.month,
                "version": sched.version,
                "status": sched.status,
                "shifts": counts,
                "total": sum(counts.values()),
            }
        )
    return history


def roster_grid_non_executive(session: Session, sched: Schedule) -> tuple[list[dict], list[int], set[int]]:
    """
    Grid roster: rows = Non-Executives, columns = Name + day numbers (1..N).
    Cell value = shift number (1, 2, or 3) or blank.
    """
    import calendar

    from config import ROLE_NON_EXECUTIVE, ROLE_NON_EXECUTIVE_BACKUP
    from services.calendar_service import get_calendar_for_month
    from services.settings_service import get_weekend_days

    _, num_days = calendar.monthrange(sched.year, sched.month)
    day_nums = list(range(1, num_days + 1))

    cal_days = get_calendar_for_month(session, sched.year, sched.month)
    nw_days = {d.date.day for d in cal_days if not d.is_working}

    primary_assigns = [
        a
        for a in sched.assignments
        if a.slot_kind == "primary"
        and a.role_snapshot in (ROLE_NON_EXECUTIVE, ROLE_NON_EXECUTIVE_BACKUP)
    ]

    # Stable name order: primary NEs first, then backup
    seen: set[str] = set()
    names: list[str] = []
    for code in (ROLE_NON_EXECUTIVE, ROLE_NON_EXECUTIVE_BACKUP):
        for a in primary_assigns:
            if a.role_snapshot == code and a.employee_name_snapshot not in seen:
                seen.add(a.employee_name_snapshot)
                names.append(a.employee_name_snapshot)

    lookup: dict[tuple[str, int], str] = {}
    for a in primary_assigns:
        lookup[(a.employee_name_snapshot, a.date.day)] = str(a.shift_number)

    rows: list[dict] = []
    for name in names:
        row: dict = {"Name": name}
        for d in day_nums:
            row[str(d)] = lookup.get((name, d), "")
        rows.append(row)

    return rows, day_nums, nw_days


def roster_grid_trainee(session: Session, sched: Schedule) -> tuple[list[dict], list[int], set[int]]:
    """Same grid layout for Trainee Engineers (trainee slots only)."""
    import calendar

    from config import ROLE_TRAINEE_ENGINEER
    from services.calendar_service import get_calendar_for_month
    from services.settings_service import get_weekend_days

    _, num_days = calendar.monthrange(sched.year, sched.month)
    day_nums = list(range(1, num_days + 1))

    cal_days = get_calendar_for_month(session, sched.year, sched.month)
    nw_days = {d.date.day for d in cal_days if not d.is_working}

    trainee_assigns = [
        a
        for a in sched.assignments
        if a.slot_kind == "trainee" and a.role_snapshot == ROLE_TRAINEE_ENGINEER
    ]

    seen: set[str] = set()
    names: list[str] = []
    for a in trainee_assigns:
        if a.employee_name_snapshot not in seen:
            seen.add(a.employee_name_snapshot)
            names.append(a.employee_name_snapshot)

    lookup: dict[tuple[str, int], str] = {}
    for a in trainee_assigns:
        lookup[(a.employee_name_snapshot, a.date.day)] = str(a.shift_number)

    rows: list[dict] = []
    for name in names:
        row: dict = {"Name": name}
        for d in day_nums:
            row[str(d)] = lookup.get((name, d), "")
        rows.append(row)

    return rows, day_nums, nw_days


def _assignment_cell_label(shift_number: int, slot_kind: str) -> str:
    """Format cell: primary 1/2/3; trainee companion slot 1t/2t."""
    if slot_kind == "trainee":
        return f"{shift_number}t"
    return str(shift_number)


def roster_grid_combined(session: Session, sched: Schedule) -> tuple[list[dict], list[int], set[int], dict[str, str]]:
    """
    Combined grid for all active staff.
    Working days with no shift duty -> G (General).
    NW days: primary shifts 1/2/3, trainee companion slots 1t/2t.
    """
    import calendar

    from config import ROLE_NON_EXECUTIVE, ROLE_NON_EXECUTIVE_BACKUP, ROLE_TRAINEE_ENGINEER
    from services.calendar_service import get_calendar_for_month
    from services.employee_service import list_employees

    _, num_days = calendar.monthrange(sched.year, sched.month)
    day_nums = list(range(1, num_days + 1))

    cal_days = get_calendar_for_month(session, sched.year, sched.month)
    nw_days = {d.date.day for d in cal_days if not d.is_working}
    working_days = set(day_nums) - nw_days
    day_types = {str(d): ("W" if d in working_days else "NW") for d in day_nums}

    # Employee order: primary NE, backup, trainees
    active = list_employees(session, active_only=True)
    names: list[str] = []
    for code in (ROLE_NON_EXECUTIVE, ROLE_NON_EXECUTIVE_BACKUP, ROLE_TRAINEE_ENGINEER):
        for e in active:
            if e.role.code == code and e.name not in names:
                names.append(e.name)

    lookup: dict[tuple[str, int], str] = {}
    for a in sched.assignments:
        label = _assignment_cell_label(a.shift_number, a.slot_kind)
        key = (a.employee_name_snapshot, a.date.day)
        lookup[key] = label

    rows: list[dict] = []
    for name in names:
        row: dict = {"Name": name}
        for d in day_nums:
            if (name, d) in lookup:
                row[str(d)] = lookup[(name, d)]
            elif d in working_days:
                row[str(d)] = "G"
            else:
                row[str(d)] = ""
        rows.append(row)

    return rows, day_nums, nw_days, day_types


def roster_grid_day_types(session: Session, sched: Schedule) -> dict[str, str]:
    """One row mapping day number -> W or NW for column headers."""
    import calendar

    from services.calendar_service import get_calendar_for_month
    from services.settings_service import get_weekend_days

    _, num_days = calendar.monthrange(sched.year, sched.month)
    cal_days = get_calendar_for_month(session, sched.year, sched.month)
    by_day = {d.date.day: d.day_type for d in cal_days}
    return {str(d): by_day.get(d, "") for d in range(1, num_days + 1)}


def grid_to_dataframe(rows: list[dict], day_nums: list[int]) -> "pd.DataFrame":
    """Build dataframe with Name first, then day columns in order."""
    import pandas as pd

    cols = ["Name"] + [str(d) for d in day_nums]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows)[cols]


def roster_dataframe_rows(session: Session, sched: Schedule) -> list[dict]:
    """Build calendar rows for display/export."""
    from services.calendar_service import get_calendar_for_month

    days = get_calendar_for_month(session, sched.year, sched.month)
    assign_map: dict[tuple, list[str]] = {}
    for a in sched.assignments:
        key = (a.date, a.shift_number, a.slot_kind)
        assign_map.setdefault(key, []).append(a.employee_name_snapshot)

    rows = []
    for day in days:
        def cell(shift: int) -> str:
            if shift not in day.required_shifts:
                return "—"
            primary = assign_map.get((day.date, shift, "primary"), [])
            trainee = assign_map.get((day.date, shift, "trainee"), [])
            if shift == 3:
                return primary[0] if primary else "VACANT"
            parts = []
            if primary:
                parts.append(primary[0])
            if trainee:
                parts.append(f"({trainee[0]})")
            return " + ".join(parts) if parts else "VACANT"

        rows.append(
            {
                "Date": day.date.strftime("%d-%m-%Y"),
                "Day": day.day_name,
                "Type": day.day_type,
                "Working/Non-Working": "Working" if day.is_working else "Non-Working",
                "1st Shift": cell(1),
                "2nd Shift": cell(2),
                "3rd Shift": cell(3),
            }
        )
    return rows


def duty_summary_rows(session: Session, sched: Schedule) -> list[dict]:
    """Duty summary per employee."""
    stats: dict[int, dict] = {}
    for a in sched.assignments:
        if a.employee_id not in stats:
            stats[a.employee_id] = {
                "Employee": a.employee_name_snapshot,
                "Role": a.role_snapshot,
                "1st Shift Count": 0,
                "2nd Shift Count": 0,
                "3rd Shift Count": 0,
                "Non-Working Duties": 0,
                "Total Duties": 0,
            }
        s = stats[a.employee_id]
        s["Total Duties"] += 1
        if a.shift_number == 1:
            s["1st Shift Count"] += 1
        elif a.shift_number == 2:
            s["2nd Shift Count"] += 1
        elif a.shift_number == 3:
            s["3rd Shift Count"] += 1

    from services.calendar_service import get_calendar_for_month

    nw_dates = {
        d.date
        for d in get_calendar_for_month(session, sched.year, sched.month)
        if not d.is_working
    }
    for a in sched.assignments:
        if a.date in nw_dates:
            stats[a.employee_id]["Non-Working Duties"] += 1

    return list(stats.values())
