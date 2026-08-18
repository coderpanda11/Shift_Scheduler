"""VPS Team members, availability, schedules, and roster display."""

from __future__ import annotations

import calendar
import json
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import BLOCKING_STATUSES, VPS_SITE_DC, VPS_SITE_DR
from models import AuditLog, VpsAssignment, VpsAvailability, VpsMember, VpsSchedule
from scheduler.calendar_util import dates_in_range, month_dates
from scheduler.vps_engine import VpsMemberInfo, generate_vps_month
from services.calendar_service import get_calendar_for_month


def list_vps_members(session: Session, site: str | None = None, active_only: bool = True) -> list[VpsMember]:
    q = select(VpsMember).order_by(VpsMember.site, VpsMember.sort_order, VpsMember.name)
    if site:
        q = q.where(VpsMember.site == site)
    if active_only:
        q = q.where(VpsMember.active.is_(True))
    return list(session.scalars(q).all())


def get_vps_member(session: Session, member_id: int) -> VpsMember | None:
    return session.get(VpsMember, member_id)


def add_vps_member(
    session: Session,
    name: str,
    staff_no: str,
    site: str,
    is_tl: bool = False,
    sort_order: int = 0,
    operator: str = "DC/In-Charge",
) -> VpsMember:
    staff = staff_no.strip()
    if session.scalar(select(VpsMember).where(VpsMember.staff_no == staff)):
        raise ValueError(f"Staff no. {staff} already exists for a VPS member")
    if is_tl and site == VPS_SITE_DC:
        for m in list_vps_members(session, site=site, active_only=False):
            if m.is_tl:
                m.is_tl = False
    member = VpsMember(
        name=name.strip(),
        staff_no=staff,
        site=site,
        is_tl=is_tl,
        sort_order=sort_order,
        active=True,
    )
    session.add(member)
    session.flush()
    session.add(
        AuditLog(
            action="vps_member_added",
            entity_type="vps_member",
            entity_id=member.id,
            new_value=f"{member.name} ({site})",
            created_by=operator,
        )
    )
    return member


def update_vps_member(
    session: Session,
    member_id: int,
    name: str | None = None,
    staff_no: str | None = None,
    site: str | None = None,
    is_tl: bool | None = None,
    sort_order: int | None = None,
    active: bool | None = None,
    operator: str = "DC/In-Charge",
) -> VpsMember:
    member = session.get(VpsMember, member_id)
    if not member:
        raise ValueError(f"VPS member {member_id} not found")
    old = f"{member.name} / {member.staff_no or ''} / {member.site}"
    if name is not None:
        member.name = name.strip()
    if staff_no is not None:
        staff = staff_no.strip()
        clash = session.scalar(
            select(VpsMember).where(VpsMember.staff_no == staff, VpsMember.id != member_id)
        )
        if clash:
            raise ValueError(f"Staff no. {staff} is already used by {clash.name}")
        member.staff_no = staff
    if site is not None:
        member.site = site
    if is_tl is not None:
        if is_tl and member.site == VPS_SITE_DC:
            for m in list_vps_members(session, site=VPS_SITE_DC, active_only=False):
                if m.id != member_id and m.is_tl:
                    m.is_tl = False
        member.is_tl = is_tl
    if sort_order is not None:
        member.sort_order = sort_order
    if active is not None:
        member.active = active
    session.add(
        AuditLog(
            action="vps_member_updated",
            entity_type="vps_member",
            entity_id=member.id,
            old_value=old,
            new_value=f"{member.name} / {member.staff_no or ''} / {member.site}",
            created_by=operator,
        )
    )
    return member


def deactivate_vps_member(
    session: Session, member_id: int, operator: str = "DC/In-Charge"
) -> VpsMember:
    return update_vps_member(session, member_id, active=False, operator=operator)


def build_vps_availability_map(
    session: Session, year: int, month: int, site: str | None = None
) -> dict[int, set[date]]:
    month_day_set = set(month_dates(year, month))
    q = select(VpsAvailability)
    if site:
        member_ids = [m.id for m in list_vps_members(session, site=site, active_only=False)]
        q = q.where(VpsAvailability.member_id.in_(member_ids))
    records = list(session.scalars(q).all())
    result: dict[int, set[date]] = {}
    for rec in records:
        if rec.status == "available":
            continue
        for d in dates_in_range(rec.start_date, rec.end_date):
            if d in month_day_set:
                result.setdefault(rec.member_id, set()).add(d)
    return result


def list_vps_availability(session: Session, member_id: int | None = None) -> list[VpsAvailability]:
    q = select(VpsAvailability).order_by(VpsAvailability.start_date.desc())
    if member_id:
        q = q.where(VpsAvailability.member_id == member_id)
    return list(session.scalars(q).all())


def add_vps_availability(
    session: Session,
    member_id: int,
    start_date: date,
    end_date: date,
    status: str,
    reason: str | None,
    operator: str,
) -> VpsAvailability:
    if start_date > end_date:
        raise ValueError("Start date must be on or before end date")
    rec = VpsAvailability(
        member_id=member_id,
        start_date=start_date,
        end_date=end_date,
        status=status.lower(),
        reason=reason,
    )
    session.add(rec)
    session.flush()
    member = session.get(VpsMember, member_id)
    session.add(
        AuditLog(
            action="vps_availability_changed",
            entity_type="vps_availability",
            entity_id=rec.id,
            new_value=f"{member.name if member else member_id}: {status}",
            reason=reason,
            created_by=operator,
        )
    )
    return rec


def delete_vps_availability(session: Session, availability_id: int, operator: str) -> None:
    rec = session.get(VpsAvailability, availability_id)
    if rec:
        session.delete(rec)
        session.add(
            AuditLog(
                action="vps_availability_deleted",
                entity_type="vps_availability",
                entity_id=availability_id,
                created_by=operator,
            )
        )


def next_vps_version(session: Session, site: str, year: int, month: int) -> int:
    max_v = session.scalar(
        select(func.max(VpsSchedule.version)).where(
            VpsSchedule.site == site,
            VpsSchedule.year == year,
            VpsSchedule.month == month,
        )
    )
    return (max_v or 0) + 1


def list_vps_schedules(
    session: Session, site: str, year: int | None = None, month: int | None = None
) -> list[VpsSchedule]:
    q = (
        select(VpsSchedule)
        .where(VpsSchedule.site == site)
        .order_by(VpsSchedule.year.desc(), VpsSchedule.month.desc(), VpsSchedule.version.desc())
    )
    if year:
        q = q.where(VpsSchedule.year == year)
    if month:
        q = q.where(VpsSchedule.month == month)
    return list(session.scalars(q).all())


def get_latest_vps_schedule(
    session: Session, site: str, year: int, month: int
) -> VpsSchedule | None:
    return session.scalar(
        select(VpsSchedule)
        .where(VpsSchedule.site == site, VpsSchedule.year == year, VpsSchedule.month == month)
        .order_by(VpsSchedule.version.desc())
        .limit(1)
    )


def generate_vps_schedule(
    session: Session,
    site: str,
    year: int,
    month: int,
    operator: str = "DC/In-Charge",
) -> VpsSchedule:
    members = list_vps_members(session, site=site)
    if not members:
        raise ValueError(f"No VPS members configured for site {site.upper()}")

    info = [
        VpsMemberInfo(m.id, m.name, m.site, m.is_tl, m.sort_order) for m in members
    ]
    avail = build_vps_availability_map(session, year, month, site=site)
    cal_days = get_calendar_for_month(session, year, month)
    working_dates = {d.date for d in cal_days if d.is_working}
    result = generate_vps_month(year, month, info, avail, working_dates)

    sched = VpsSchedule(
        site=site,
        year=year,
        month=month,
        version=next_vps_version(session, site, year, month),
        status="draft",
        explanation_json=json.dumps({"text": result.explanation}),
        created_by=operator,
    )
    session.add(sched)
    session.flush()

    for a in result.assignments:
        session.add(
            VpsAssignment(
                schedule_id=sched.id,
                date=a.date,
                shift_number=a.shift_number,
                member_id=a.member_id,
                member_name_snapshot=a.member_name,
                is_carry_over=a.is_carry_over,
            )
        )

    session.add(
        AuditLog(
            action="vps_schedule_generated",
            entity_type="vps_schedule",
            entity_id=sched.id,
            new_value=f"{site.upper()} {year}-{month:02d} v{sched.version}",
            created_by=operator,
        )
    )
    return sched


def publish_vps_schedule(session: Session, schedule_id: int, operator: str) -> VpsSchedule:
    sched = session.get(VpsSchedule, schedule_id)
    if not sched:
        raise ValueError("VPS schedule not found")
    sched.status = "published"
    sched.published_at = datetime.utcnow()
    session.add(
        AuditLog(
            action="vps_schedule_published",
            entity_type="vps_schedule",
            entity_id=sched.id,
            new_value=f"v{sched.version}",
            created_by=operator,
        )
    )
    return sched


def vps_roster_grid(
    session: Session, sched: VpsSchedule
) -> tuple[list[dict], list[int], set[int], dict[str, str]]:
    """Build VPS roster grid rows for one site schedule."""
    _, num_days = calendar.monthrange(sched.year, sched.month)
    day_nums = list(range(1, num_days + 1))
    cal_days = get_calendar_for_month(session, sched.year, sched.month)
    nw_days = {d.date.day for d in cal_days if not d.is_working}
    working_days = set(day_nums) - nw_days
    day_types = {str(d): ("W" if d in working_days else "NW") for d in day_nums}

    members = list_vps_members(session, site=sched.site, active_only=True)
    avail = build_vps_availability_map(session, sched.year, sched.month, site=sched.site)

    # member -> day -> label (only one primary label per day; carry-over may double-count in assignments)
    lookup: dict[tuple[str, int], str] = {}
    for a in sched.assignments:
        if a.shift_number == 0:
            label = "G"
        else:
            label = str(a.shift_number)
            if a.is_carry_over:
                label += "*"
        key = (a.member_name_snapshot, a.date.day)
        if key in lookup and a.shift_number > 0:
            lookup[key] = lookup[key] + "/" + label.replace("*", "") + ("*" if a.is_carry_over else "")
        else:
            lookup[key] = label

    rows: list[dict] = []
    for m in members:
        row: dict = {"Name": m.name}
        for d in day_nums:
            if (m.name, d) in lookup:
                row[str(d)] = lookup[(m.name, d)]
            elif m.is_tl and d in working_days:
                row[str(d)] = "G"
            else:
                row[str(d)] = "X"
        for blocked in avail.get(m.id, set()):
            row[str(blocked.day)] = "NA"
        rows.append(row)

    return rows, day_nums, nw_days, day_types
