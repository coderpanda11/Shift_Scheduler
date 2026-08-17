"""Schedule validation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from config import BLOCKING_STATUSES, ROLE_NON_EXECUTIVE, ROLE_NON_EXECUTIVE_BACKUP
from scheduler.fairness import EmployeeInfo, SlotInfo


@dataclass
class Assignment:
    """Generated assignment record."""

    date: date
    shift_number: int
    slot_kind: str
    employee_id: int
    employee_name: str
    role_code: str
    is_working_day: bool


@dataclass
class ValidationResult:
    """Result of schedule validation."""

    quality: str  # good | warning | conflict
    conflicts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)

    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


def validate_schedule(
    assignments: list[Assignment],
    required_slots: list[SlotInfo],
    employees: dict[int, EmployeeInfo],
    availability_map: dict[int, set[date]],
    mode: str,
    rules: dict,
) -> ValidationResult:
    """Validate generated schedule against hard and soft constraints."""
    result = ValidationResult(quality="good")

    filled = {(a.date, a.shift_number, a.slot_kind) for a in assignments}
    for slot in required_slots:
        key = (slot.date, slot.shift_number, slot.slot_kind)
        if key not in filled:
            result.conflicts.append(
                f"Vacant slot: {slot.date} shift {slot.shift_number} ({slot.slot_kind})"
            )

    # Unavailable assigned
    for a in assignments:
        blocked = availability_map.get(a.employee_id, set())
        if a.date in blocked:
            result.conflicts.append(
                f"{a.employee_name} assigned on unavailable date {a.date}"
            )

    # Inactive employees
    for a in assignments:
        emp = employees.get(a.employee_id)
        if emp and not emp.active:
            result.conflicts.append(f"Inactive employee {a.employee_name} assigned")

    # Double shift same day
    by_date: dict[tuple[date, int], list[Assignment]] = {}
    for a in assignments:
        by_date.setdefault((a.date, a.employee_id), []).append(a)
    for (d, eid), group in by_date.items():
        if len(group) > 1:
            emp_name = group[0].employee_name
            result.conflicts.append(f"{emp_name} has {len(group)} shifts on {d}")

    # Duplicate on same shift
    by_shift: dict[tuple[date, int, str], list[Assignment]] = {}
    for a in assignments:
        by_shift.setdefault((a.date, a.shift_number, a.slot_kind), []).append(a)
    for key, group in by_shift.items():
        if len(group) > 1:
            result.conflicts.append(f"Duplicate assignment on {key}")

    # Trainee on 3rd shift
    for a in assignments:
        if a.shift_number == 3 and a.role_code == "TRAINEE_ENGINEER":
            result.conflicts.append(f"Trainee {a.employee_name} on 3rd shift {a.date}")

    # Backup in ideal mode
    if mode == "ideal":
        for a in assignments:
            if a.role_code == ROLE_NON_EXECUTIVE_BACKUP:
                result.warnings.append(
                    f"Backup {a.employee_name} used in IDEAL mode on {a.date}"
                )

    # Fairness checks for primary NEs
    primary_ids = [
        eid for eid, e in employees.items() if e.role_code == ROLE_NON_EXECUTIVE
    ]
    ne_stats = _duty_stats(assignments, primary_ids)
    if ne_stats:
        totals = [s["total"] for s in ne_stats.values()]
        diff = max(totals) - min(totals)
        if diff > 1:
            result.warnings.append(
                f"Primary Non-Executive total duty difference is {diff} (preferred ≤1)"
            )
        for shift in (2, 3):
            counts = [ne_stats[eid]["shifts"].get(shift, 0) for eid in primary_ids if eid in ne_stats]
            if counts and max(counts) - min(counts) > 1:
                result.warnings.append(
                    f"Shift {shift} imbalance among primary Non-Executives"
                )
        first_counts = [ne_stats[eid]["shifts"].get(1, 0) for eid in primary_ids if eid in ne_stats]
        if first_counts and max(first_counts) - min(first_counts) > 1:
            result.warnings.append(
                "Non-working 1st shift imbalance among primary Non-Executives"
            )

    # Trainee fairness
    trainee_ids = [
        eid for eid, e in employees.items() if e.role_code == "TRAINEE_ENGINEER"
    ]
    tr_stats = _duty_stats(
        [a for a in assignments if a.slot_kind == "trainee"], trainee_ids
    )
    if tr_stats:
        totals = [s["total"] for s in tr_stats.values()]
        if totals and max(totals) - min(totals) > 1:
            result.warnings.append("Trainee duty difference exceeds 1")

    # Consecutive thirds
    max_consec = rules.get("max_consecutive_third_shifts", 2)
    for eid in employees:
        consec = _max_consecutive_thirds(assignments, eid)
        if consec > max_consec:
            emp = employees[eid]
            result.warnings.append(
                f"{emp.name} has {consec} consecutive Third Shifts"
            )

    result.checks = {
        "all_slots_filled": not any("Vacant" in c for c in result.conflicts),
        "no_unavailable": not any("unavailable" in c for c in result.conflicts),
        "no_double_shift": not any("shifts on" in c for c in result.conflicts),
    }

    if result.conflicts:
        result.quality = "conflict"
    elif result.warnings:
        result.quality = "warning"
    else:
        result.quality = "good"

    return result


def _duty_stats(
    assignments: list[Assignment], employee_ids: list[int]
) -> dict[int, dict[str, Any]]:
    stats: dict[int, dict] = {}
    for eid in employee_ids:
        stats[eid] = {"total": 0, "shifts": {1: 0, 2: 0, 3: 0}, "nwd": 0}
    for a in assignments:
        if a.employee_id not in stats:
            continue
        stats[a.employee_id]["total"] += 1
        stats[a.employee_id]["shifts"][a.shift_number] = (
            stats[a.employee_id]["shifts"].get(a.shift_number, 0) + 1
        )
        if not a.is_working_day:
            stats[a.employee_id]["nwd"] += 1
    return stats


def _max_consecutive_thirds(assignments: list[Assignment], employee_id: int) -> int:
    third_dates = sorted(
        a.date for a in assignments if a.employee_id == employee_id and a.shift_number == 3
    )
    if not third_dates:
        return 0
    max_run = 1
    run = 1
    for i in range(1, len(third_dates)):
        if (third_dates[i] - third_dates[i - 1]).days == 1:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1
    return max_run


def build_explanation(
    assignments: list[Assignment],
    employees: dict[int, EmployeeInfo],
    mode: str,
    unavailable_ranges: list[dict],
    validation: ValidationResult,
) -> dict:
    """Build 'Why this schedule?' explanation."""
    primary_ids = [
        eid for eid, e in employees.items() if e.role_code == ROLE_NON_EXECUTIVE
    ]
    backup_ids = [
        eid for eid, e in employees.items() if e.role_code == ROLE_NON_EXECUTIVE_BACKUP
    ]
    ne_stats = _duty_stats(assignments, primary_ids + backup_ids)

    lines = [
        f"Scheduling mode: {mode.upper().replace('_', ' / ')}",
        f"Primary Non-Executives available: {len(primary_ids)}",
    ]
    for r in unavailable_ranges:
        lines.append(
            f"{r.get('name', '?')} unavailable: {r.get('start')} to {r.get('end')} ({r.get('reason', '')})"
        )

    lines.append("\nNon-Executive duty distribution:")
    for eid in primary_ids + backup_ids:
        emp = employees[eid]
        s = ne_stats.get(eid, {"total": 0, "shifts": {1: 0, 2: 0, 3: 0}})
        lines.append(
            f"  {emp.name}: total={s['total']}, "
            f"1st={s['shifts'].get(1,0)}, 2nd={s['shifts'].get(2,0)}, 3rd={s['shifts'].get(3,0)}"
        )

    if primary_ids:
        totals = [ne_stats.get(eid, {}).get("total", 0) for eid in primary_ids]
        if totals:
            lines.append(f"\nDifference (highest - lowest primary NE): {max(totals) - min(totals)}")

    trainee_ids = [
        eid for eid, e in employees.items() if e.role_code == "TRAINEE_ENGINEER"
    ]
    tr_stats = _duty_stats(
        [a for a in assignments if a.slot_kind == "trainee"], trainee_ids
    )
    lines.append("\nTrainee duty distribution:")
    for eid in trainee_ids:
        emp = employees[eid]
        t = tr_stats.get(eid, {"total": 0})
        lines.append(f"  {emp.name}: {t['total']}")

    lines.append(f"\nSchedule Quality: {validation.quality.upper()}")
    lines.append(f"Conflicts: {validation.conflict_count}, Warnings: {validation.warning_count}")

    return {
        "mode": mode,
        "lines": lines,
        "text": "\n".join(lines),
        "ne_stats": {str(k): v for k, v in ne_stats.items()},
        "trainee_stats": {str(k): v for k, v in tr_stats.items()},
    }
