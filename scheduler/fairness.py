"""Fairness scoring and employee counters for scheduling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from config import ROLE_NON_EXECUTIVE, ROLE_NON_EXECUTIVE_BACKUP, ROLE_TRAINEE_ENGINEER


@dataclass
class EmployeeInfo:
    """Lightweight employee for scheduling (no ORM dependency)."""

    id: int
    name: str
    role_code: str
    active: bool = True


@dataclass
class EmployeeCounters:
    """Running duty counters for one employee during schedule generation."""

    employee_id: int
    total_duties: int = 0
    shift_counts: dict[int, int] = field(default_factory=lambda: {1: 0, 2: 0, 3: 0})
    non_working_duties: int = 0
    first_shift_count: int = 0
    last_duty_date: Optional[date] = None
    consecutive_thirds: int = 0
    prior_month_shift_counts: dict[int, int] = field(default_factory=dict)


@dataclass
class SlotInfo:
    """A single duty slot to fill."""

    date: date
    shift_number: int
    slot_kind: str  # primary | trainee
    is_working_day: bool


def init_counters(
    employees: list[EmployeeInfo],
    prior_stats: dict[int, dict] | None = None,
) -> dict[int, EmployeeCounters]:
    """Initialize counters for all employees."""
    prior_stats = prior_stats or {}
    counters: dict[int, EmployeeCounters] = {}
    for emp in employees:
        ps = prior_stats.get(emp.id, {})
        counters[emp.id] = EmployeeCounters(
            employee_id=emp.id,
            prior_month_shift_counts=ps.get("shift_counts", {}),
        )
    return counters


def order_slots(slots: list[SlotInfo]) -> list[SlotInfo]:
    """Fill harder slots first: 3rd primary, 1st primary, 2nd primary, then trainees."""
    priority = {
        ("primary", 3): 0,
        ("primary", 1): 1,
        ("primary", 2): 2,
        ("trainee", 1): 3,
        ("trainee", 2): 4,
    }

    def key(s: SlotInfo) -> tuple:
        return (priority.get((s.slot_kind, s.shift_number), 99), s.date, s.shift_number)

    return sorted(slots, key=key)


def expand_slots(days: list) -> list[SlotInfo]:
    """Expand classified days into individual slots."""
    slots: list[SlotInfo] = []
    for day in days:
        for shift in day.required_shifts:
            slots.append(
                SlotInfo(
                    date=day.date,
                    shift_number=shift,
                    slot_kind="primary",
                    is_working_day=day.is_working,
                )
            )
            if shift in (1, 2):
                slots.append(
                    SlotInfo(
                        date=day.date,
                        shift_number=shift,
                        slot_kind="trainee",
                        is_working_day=day.is_working,
                    )
                )
    return slots


def calculate_candidate_score(
    emp: EmployeeInfo,
    slot: SlotInfo,
    counters: EmployeeCounters,
    rules: dict,
    weights: dict,
    mode: str,
    primary_ne_unavailable: bool,
    nw_shortage: bool,
    recent_duty_count: int,
) -> float:
    """Lower score = better candidate."""
    w = weights
    score = 0.0

    score += counters.total_duties * w.get("total_duties", 10)
    score += counters.shift_counts.get(slot.shift_number, 0) * w.get("same_shift", 8)

    if not slot.is_working_day:
        score += counters.non_working_duties * w.get("non_working_day", 5)
    if slot.shift_number == 1:
        score += counters.first_shift_count * w.get("first_shift", 6)

    if slot.shift_number == 3 and counters.consecutive_thirds > 0:
        score += counters.consecutive_thirds * w.get("consecutive_third_penalty", 15)

    score += recent_duty_count * w.get("recent_duty", 3)

    # Backup rules
    if emp.role_code == ROLE_NON_EXECUTIVE_BACKUP:
        if mode == "ideal":
            score += w.get("backup_ideal_penalty", 10000)
        if slot.shift_number != 3:
            score += w.get("backup_non_third_penalty", 10000)
        elif nw_shortage and not slot.is_working_day and slot.slot_kind == "primary":
            score += w.get("backup_nw_third_bonus", -50)

    # Trainee on primary slot
    if emp.role_code == ROLE_TRAINEE_ENGINEER and slot.slot_kind == "primary":
        if slot.is_working_day:
            if mode == "ideal" or not primary_ne_unavailable or slot.shift_number != 2:
                score += w.get("trainee_on_primary_ideal_penalty", 10000)
            else:
                score += w.get("trainee_on_primary_shortage_bonus", -50)
        elif nw_shortage and mode == "backup_rebalanced" and slot.shift_number in (1, 2):
            score += w.get("trainee_on_primary_shortage_bonus", -50)
        else:
            score += w.get("trainee_on_primary_ideal_penalty", 10000)

    # NW shortage: trainees should not take trainee companion slots (NE fills those)
    if (
        emp.role_code == ROLE_TRAINEE_ENGINEER
        and slot.slot_kind == "trainee"
        and nw_shortage
        and not slot.is_working_day
    ):
        score += w.get("trainee_on_trainee_slot_nw_shortage_penalty", 10000)

    # NW shortage: prefer NE on trainee companion slots
    if (
        emp.role_code == ROLE_NON_EXECUTIVE
        and slot.slot_kind == "trainee"
        and nw_shortage
        and not slot.is_working_day
    ):
        score += w.get("trainee_on_primary_shortage_bonus", -50)

    if rules.get("cross_month_fairness") and counters.prior_month_shift_counts:
        score += counters.prior_month_shift_counts.get(
            slot.shift_number, 0
        ) * w.get("cross_month_shift", 2)

    return score


def tie_break_key(
    emp: EmployeeInfo,
    counters: EmployeeCounters,
    slot_date: date,
) -> tuple:
    """Deterministic tie-break: fewer duties, longer since last duty, lower id."""
    days_since = 9999
    if counters.last_duty_date:
        days_since = (slot_date - counters.last_duty_date).days
    return (counters.total_duties, -days_since, emp.id)


def update_counters_after_assignment(
    counters: EmployeeCounters,
    slot: SlotInfo,
    prev_shift_on_date: int | None,
) -> None:
    """Update counters after assigning a slot."""
    counters.total_duties += 1
    counters.shift_counts[slot.shift_number] = (
        counters.shift_counts.get(slot.shift_number, 0) + 1
    )
    if not slot.is_working_day:
        counters.non_working_duties += 1
    if slot.shift_number == 1:
        counters.first_shift_count += 1

    if slot.shift_number == 3:
        counters.consecutive_thirds += 1
    else:
        counters.consecutive_thirds = 0

    counters.last_duty_date = slot.date


def is_primary_ne(emp: EmployeeInfo) -> bool:
    return emp.role_code == ROLE_NON_EXECUTIVE


def is_backup(emp: EmployeeInfo) -> bool:
    return emp.role_code == ROLE_NON_EXECUTIVE_BACKUP


def is_trainee(emp: EmployeeInfo) -> bool:
    return emp.role_code == ROLE_TRAINEE_ENGINEER


def eligible_for_slot(
    emp: EmployeeInfo,
    slot: SlotInfo,
    mode: str,
    rules: dict,
    primary_ne_unavailable: bool,
    nw_shortage: bool = False,
) -> bool:
    """Role eligibility for a slot."""
    if not emp.active:
        return False

    if slot.slot_kind == "trainee":
        if nw_shortage and not slot.is_working_day and rules.get("nw_shortage_ne_on_trainee_slot", True):
            return emp.role_code == ROLE_NON_EXECUTIVE
        return emp.role_code == ROLE_TRAINEE_ENGINEER

    # Primary slot
    if slot.shift_number == 3:
        if emp.role_code == ROLE_NON_EXECUTIVE:
            return True
        if emp.role_code == ROLE_NON_EXECUTIVE_BACKUP:
            return mode == "backup_rebalanced" and (primary_ne_unavailable or nw_shortage)
        return False

    if slot.shift_number in (1, 2):
        if emp.role_code == ROLE_NON_EXECUTIVE:
            return True
        if emp.role_code == ROLE_NON_EXECUTIVE_BACKUP:
            if slot.shift_number == 1 and rules.get("backup_on_first_shift"):
                return mode == "backup_rebalanced"
            if slot.shift_number == 2 and rules.get("backup_on_second_shift"):
                return mode == "backup_rebalanced"
            return False
        if emp.role_code == ROLE_TRAINEE_ENGINEER:
            if slot.is_working_day:
                return (
                    slot.shift_number == 2
                    and mode == "backup_rebalanced"
                    and primary_ne_unavailable
                )
            if nw_shortage and mode == "backup_rebalanced" and rules.get("nw_shortage_trainee_on_primary", True):
                return slot.shift_number in (1, 2)
            return False

    return False
