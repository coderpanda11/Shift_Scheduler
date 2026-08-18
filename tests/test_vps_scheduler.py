"""VPS Team scheduler tests."""

from datetime import date

from config import VPS_SITE_DC
from models import VpsAvailability, VpsMember
from scheduler.vps_engine import VpsMemberInfo, assign_day, generate_vps_month
from services.calendar_service import get_calendar_for_month
from services.vps_service import generate_vps_schedule, list_vps_members, vps_roster_grid


def test_tl_general_on_working_days_only(db_session):
    members = list_vps_members(db_session, site=VPS_SITE_DC)
    info = [VpsMemberInfo(m.id, m.name, m.site, m.is_tl, m.sort_order) for m in members]
    cal = get_calendar_for_month(db_session, 2026, 9)
    working = {d.date for d in cal if d.is_working}
    nw = {d.date for d in cal if not d.is_working}
    result = generate_vps_month(2026, 9, info, {}, working)
    tl = next(m for m in members if m.is_tl)
    tl_by_date = {a.date: a for a in result.assignments if a.member_id == tl.id}
    assert len(tl_by_date) == len(working)
    assert all(a.shift_number == 0 for a in tl_by_date.values())
    for d in nw:
        assert d not in tl_by_date


def test_carry_over_when_next_unavailable(db_session):
    workers = [
        VpsMemberInfo(1, "M1", "dc", False, 1),
        VpsMemberInfo(2, "M2", "dc", False, 2),
        VpsMemberInfo(3, "M3", "dc", False, 3),
    ]
    day = date(2026, 9, 15)
    availability = {2: {day}}  # M2 unavailable
    assigns, _, notes = assign_day(day, workers, availability, day_offset=2)
    shift_by_num = {a.shift_number: a for a in assigns if a.shift_number > 0}
    assert shift_by_num[1].member_name == "M3"
    assert shift_by_num[2].member_name == "M1"
    assert shift_by_num[3].member_name == "M1"
    assert shift_by_num[3].is_carry_over
    assert any("continues" in n for n in notes)


def test_vps_generate_and_grid(db_session):
    sched = generate_vps_schedule(db_session, VPS_SITE_DC, 2026, 9, operator="test")
    rows, day_nums, _, _ = vps_roster_grid(db_session, sched)
    cal = get_calendar_for_month(db_session, 2026, 9)
    working_days = {d.date.day for d in cal if d.is_working}
    nw_days = {d.date.day for d in cal if not d.is_working}
    tl_row = next(r for r in rows if "TL" in r["Name"])
    for d in working_days:
        assert tl_row.get(str(d)) == "G"
    for d in nw_days:
        assert tl_row.get(str(d)) == "X"


def test_unavailable_shows_na(db_session):
    member = db_session.query(VpsMember).filter(VpsMember.staff_no == "VPS-DC2").one()
    db_session.add(
        VpsAvailability(
            member_id=member.id,
            start_date=date(2026, 9, 5),
            end_date=date(2026, 9, 5),
            status="leave",
        )
    )
    db_session.commit()
    sched = generate_vps_schedule(db_session, VPS_SITE_DC, 2026, 9, operator="test")
    rows, _, _, _ = vps_roster_grid(db_session, sched)
    m2 = next(r for r in rows if r["Name"] == member.name)
    assert m2["5"] == "NA"


def test_shifts_rotate_across_days():
    workers = [
        VpsMemberInfo(1, "M1", "dc", False, 1),
        VpsMemberInfo(2, "M2", "dc", False, 2),
        VpsMemberInfo(3, "M3", "dc", False, 3),
    ]
    from scheduler.calendar_util import month_dates

    working = set(month_dates(2026, 9))
    result = generate_vps_month(2026, 9, workers, {}, working)
    day1 = date(2026, 9, 1)
    day2 = date(2026, 9, 2)

    def shifts_on(d):
        return {
            a.shift_number: a.member_name
            for a in result.assignments
            if a.date == d and a.shift_number > 0
        }

    assert shifts_on(day1) == {1: "M1", 2: "M2", 3: "M3"}
    assert shifts_on(day2) == {1: "M2", 2: "M3", 3: "M1"}


def test_nw_days_no_shifts_show_x(db_session):
    sched = generate_vps_schedule(db_session, VPS_SITE_DC, 2026, 9, operator="test")
    cal = get_calendar_for_month(db_session, 2026, 9)
    nw_days = {d.date.day for d in cal if not d.is_working}
    assert nw_days

    for a in sched.assignments:
        if a.shift_number > 0:
            assert a.date.day not in nw_days

    rows, _, _, _ = vps_roster_grid(db_session, sched)
    tl_row = next(r for r in rows if "TL" in r["Name"])
    member = next(r for r in rows if "TL" not in r["Name"])
    for d in nw_days:
        assert member[str(d)] == "X"
        assert tl_row[str(d)] == "X"
