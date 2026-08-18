"""VPS Team shift scheduler — DC/DR sites with TL=General and carry-over rule."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from scheduler.calendar_util import month_dates


@dataclass
class VpsMemberInfo:
    id: int
    name: str
    site: str
    is_tl: bool
    sort_order: int


@dataclass
class VpsDayAssignment:
    date: date
    member_id: int
    member_name: str
    shift_number: int  # 0=General, 1-3=shift
    is_carry_over: bool = False


@dataclass
class VpsScheduleResult:
    assignments: list[VpsDayAssignment] = field(default_factory=list)
    explanation: str = ""


def _is_blocked(member_id: int, day: date, availability: dict[int, set[date]]) -> bool:
    return day in availability.get(member_id, set())


def _next_available(
    workers: list[VpsMemberInfo],
    day: date,
    availability: dict[int, set[date]],
    start_idx: int,
) -> tuple[VpsMemberInfo | None, int]:
    """First available worker from rotation index; returns (member, new_index)."""
    for offset in range(len(workers)):
        idx = (start_idx + offset) % len(workers)
        w = workers[idx]
        if not _is_blocked(w.id, day, availability):
            return w, idx + 1
    return None, start_idx


def assign_day(
    day: date,
    members: list[VpsMemberInfo],
    availability: dict[int, set[date]],
    day_offset: int,
    is_working: bool = True,
) -> tuple[list[VpsDayAssignment], int, list[str]]:
    """Assign one day for a VPS site. Returns assignments, next day offset, notes."""
    assignments: list[VpsDayAssignment] = []
    notes: list[str] = []
    tl = next((m for m in members if m.is_tl), None)
    workers = sorted([m for m in members if not m.is_tl], key=lambda m: m.sort_order)

    if tl and is_working:
        assignments.append(
            VpsDayAssignment(day, tl.id, tl.name, shift_number=0, is_carry_over=False)
        )

    if not is_working or not workers:
        return assignments, day_offset + 1, notes

    prev: VpsMemberInfo | None = None
    n = len(workers)

    for shift in (1, 2, 3):
        planned = workers[(day_offset + shift - 1) % n]
        carry = False

        if _is_blocked(planned.id, day, availability):
            if prev and not _is_blocked(prev.id, day, availability):
                assignee = prev
                carry = True
                notes.append(
                    f"{day}: shift {shift} — {planned.name} unavailable; "
                    f"{prev.name} continues from shift {shift - 1}"
                )
            else:
                fallback, _ = _next_available(workers, day, availability, day_offset + shift)
                if not fallback:
                    notes.append(f"{day}: shift {shift} — no available member")
                    continue
                assignee = fallback
                notes.append(
                    f"{day}: shift {shift} — {planned.name} unavailable; assigned {fallback.name}"
                )
        else:
            assignee = planned

        assignments.append(
            VpsDayAssignment(day, assignee.id, assignee.name, shift, is_carry_over=carry)
        )
        if not carry:
            prev = assignee

    return assignments, day_offset + 1, notes


def generate_vps_month(
    year: int,
    month: int,
    members: list[VpsMemberInfo],
    availability: dict[int, set[date]],
    working_dates: set[date] | None = None,
) -> VpsScheduleResult:
    """Build a full month VPS roster for one site."""
    days = month_dates(year, month)
    if working_dates is None:
        working_dates = set(days)

    all_assignments: list[VpsDayAssignment] = []
    all_notes: list[str] = []
    day_offset = 0

    for day in days:
        is_working = day in working_dates
        day_assigns, day_offset, notes = assign_day(
            day, members, availability, day_offset, is_working
        )
        all_assignments.extend(day_assigns)
        all_notes.extend(notes)

    site_label = members[0].site.upper() if members else "?"
    explanation = (
        f"VPS {site_label} schedule for {month:02d}/{year}. "
        f"TL General (G) on working days only. Shifts rotate daily. "
        f"NW days: all members off (X). "
        f"Unavailable member → previous shift holder continues. "
    )
    if all_notes:
        explanation += "Carry-overs: " + "; ".join(all_notes[:20])
        if len(all_notes) > 20:
            explanation += f" … (+{len(all_notes) - 20} more)"
    else:
        explanation += "No carry-overs required."

    return VpsScheduleResult(assignments=all_assignments, explanation=explanation)
