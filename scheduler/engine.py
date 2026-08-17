"""Core scheduling engine — independent of Streamlit."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from config import BLOCKING_STATUSES, ROLE_NON_EXECUTIVE
from scheduler.calendar_util import classify_month, expand_holidays_for_month, month_dates
from scheduler.fairness import (
    EmployeeCounters,
    EmployeeInfo,
    SlotInfo,
    calculate_candidate_score,
    eligible_for_slot,
    expand_slots,
    init_counters,
    is_primary_ne,
    order_slots,
    tie_break_key,
    update_counters_after_assignment,
)
from scheduler.validator import Assignment, ValidationResult, build_explanation, validate_schedule

logger = logging.getLogger(__name__)


@dataclass
class ScheduleContext:
    """Input context for schedule generation."""

    year: int
    month: int
    employees: list[EmployeeInfo]
    availability_map: dict[int, set[date]]  # employee_id -> blocked dates
    weekend_days: list[int]
    saturday_rule: str
    holidays: list[tuple[date, bool]]  # (date, repeats_yearly)
    date_overrides: dict[date, bool]
    rules: dict
    weights: dict
    prior_month_stats: dict[int, dict] | None = None


@dataclass
class ScheduleResult:
    """Output of schedule generation."""

    assignments: list[Assignment] = field(default_factory=list)
    mode: str = "ideal"
    validation: Optional[ValidationResult] = None
    explanation: dict = field(default_factory=dict)
    days: list = field(default_factory=list)
    required_slots: list[SlotInfo] = field(default_factory=list)
    vacant_slots: list[SlotInfo] = field(default_factory=list)


class ScheduleEngine:
    """Deterministic weighted-fair scheduling engine."""

    def generate_schedule(self, context: ScheduleContext) -> ScheduleResult:
        """Generate a full monthly schedule."""
        holiday_dates = expand_holidays_for_month(
            context.year, context.month, context.holidays
        )
        days = classify_month(
            context.year,
            context.month,
            context.weekend_days,
            holiday_dates,
            context.date_overrides,
            context.saturday_rule,
        )
        slots = expand_slots(days)
        ordered = order_slots(slots)

        employees_by_id = {e.id: e for e in context.employees}
        primary_nes = [e for e in context.employees if is_primary_ne(e)]
        mode = self._determine_mode(primary_nes, context)
        counters = init_counters(context.employees, context.prior_month_stats)

        assignments: list[Assignment] = []
        assigned_by_date: dict[date, set[int]] = {}
        assignment_history: list[tuple[date, int, int]] = []  # date, emp_id, shift
        vacant: list[SlotInfo] = []

        for slot in ordered:
            primary_ne_unavail = self._primary_ne_unavailable_on(
                slot.date, primary_nes, context.availability_map
            )
            nw_shortage = (
                not slot.is_working_day
                and mode == "backup_rebalanced"
                and primary_ne_unavail
            )
            candidates = self._get_eligible_employees(
                slot, context, mode, primary_ne_unavail, nw_shortage, assigned_by_date, assignment_history
            )
            if not candidates:
                vacant.append(slot)
                logger.warning("No candidate for %s shift %s %s", slot.date, slot.shift_number, slot.slot_kind)
                continue

            best = self._pick_best_candidate(
                candidates,
                slot,
                counters,
                context,
                mode,
                primary_ne_unavail,
                nw_shortage,
                assignment_history,
            )
            emp = employees_by_id[best]
            assignments.append(
                Assignment(
                    date=slot.date,
                    shift_number=slot.shift_number,
                    slot_kind=slot.slot_kind,
                    employee_id=emp.id,
                    employee_name=emp.name,
                    role_code=emp.role_code,
                    is_working_day=slot.is_working_day,
                )
            )
            assigned_by_date.setdefault(slot.date, set()).add(emp.id)
            assignment_history.append((slot.date, emp.id, slot.shift_number))
            update_counters_after_assignment(counters[emp.id], slot, None)

        unavailable_ranges = self._unavailable_ranges(primary_nes, context)
        validation = validate_schedule(
            assignments,
            ordered,
            employees_by_id,
            context.availability_map,
            mode,
            context.rules,
        )
        explanation = build_explanation(
            assignments, employees_by_id, mode, unavailable_ranges, validation
        )

        return ScheduleResult(
            assignments=assignments,
            mode=mode,
            validation=validation,
            explanation=explanation,
            days=days,
            required_slots=ordered,
            vacant_slots=vacant,
        )

    def _determine_mode(
        self, primary_nes: list[EmployeeInfo], context: ScheduleContext
    ) -> str:
        """IDEAL if all primary NEs available entire month."""
        month_days = set(month_dates(context.year, context.month))
        for emp in primary_nes:
            blocked = context.availability_map.get(emp.id, set())
            if blocked & month_days:
                return "backup_rebalanced"
        return "ideal"

    def _primary_ne_unavailable_on(
        self,
        d: date,
        primary_nes: list[EmployeeInfo],
        availability_map: dict[int, set[date]],
    ) -> bool:
        """True if any primary NE is unavailable on this date."""
        for emp in primary_nes:
            if d in availability_map.get(emp.id, set()):
                return True
        return False

    def _get_eligible_employees(
        self,
        slot: SlotInfo,
        context: ScheduleContext,
        mode: str,
        primary_ne_unavail: bool,
        nw_shortage: bool,
        assigned_by_date: dict[date, set[int]],
        assignment_history: list[tuple[date, int, int]],
    ) -> list[int]:
        """Find eligible employee IDs for a slot."""
        result: list[int] = []
        for emp in context.employees:
            if not emp.active:
                continue
            if slot.date in context.availability_map.get(emp.id, set()):
                continue
            if emp.id in assigned_by_date.get(slot.date, set()):
                continue
            if not eligible_for_slot(
                emp, slot, mode, context.rules, primary_ne_unavail, nw_shortage
            ):
                continue
            if context.rules.get("avoid_third_then_first") and slot.shift_number == 1:
                yesterday = slot.date - timedelta(days=1)
                if any(d == yesterday and e == emp.id and sh == 3 for d, e, sh in assignment_history):
                    continue
            result.append(emp.id)
        return result

    def _pick_best_candidate(
        self,
        candidate_ids: list[int],
        slot: SlotInfo,
        counters: dict[int, EmployeeCounters],
        context: ScheduleContext,
        mode: str,
        primary_ne_unavail: bool,
        nw_shortage: bool,
        assignment_history: list[tuple[date, int, int]],
    ) -> int:
        """Pick lowest score with tie-break."""
        employees_by_id = {e.id: e for e in context.employees}
        window = context.rules.get("recent_duty_window_days", 7)

        def score_for(eid: int) -> tuple:
            emp = employees_by_id[eid]
            recent = sum(
                1
                for d, e, _ in assignment_history
                if e == eid and (slot.date - d).days <= window
            )
            # Third then first penalty
            extra = 0.0
            if context.rules.get("avoid_third_then_first") and slot.shift_number == 1:
                yesterday = slot.date - timedelta(days=1)
                for d, e, sh in assignment_history:
                    if e == eid and d == yesterday and sh == 3:
                        extra += context.weights.get("third_then_first_penalty", 20)

            base = calculate_candidate_score(
                emp,
                slot,
                counters[eid],
                context.rules,
                context.weights,
                mode,
                primary_ne_unavail,
                nw_shortage,
                recent,
            )
            base += extra
            tb = tie_break_key(emp, counters[eid], slot.date)
            return (base, tb)

        return min(candidate_ids, key=score_for)

    def _unavailable_ranges(
        self, primary_nes: list[EmployeeInfo], context: ScheduleContext
    ) -> list[dict]:
        """Summarize unavailable ranges for explanation."""
        ranges: list[dict] = []
        for emp in primary_nes:
            blocked = sorted(context.availability_map.get(emp.id, set()))
            if not blocked:
                continue
            start = blocked[0]
            end = blocked[0]
            for d in blocked[1:]:
                if (d - end).days == 1:
                    end = d
                else:
                    ranges.append(
                        {"name": emp.name, "start": str(start), "end": str(end), "reason": "unavailable"}
                    )
                    start = end = d
            ranges.append(
                {"name": emp.name, "start": str(start), "end": str(end), "reason": "unavailable"}
            )
        return ranges

    def validate_schedule(
        self,
        assignments: list[Assignment],
        required_slots: list[SlotInfo],
        employees: dict[int, EmployeeInfo],
        availability_map: dict[int, set[date]],
        mode: str,
        rules: dict,
    ) -> ValidationResult:
        """Public validation wrapper."""
        return validate_schedule(
            assignments, required_slots, employees, availability_map, mode, rules
        )

    def rebalance_schedule(self, context: ScheduleContext) -> ScheduleResult:
        """Regenerate from scratch (no patch-in-place)."""
        return self.generate_schedule(context)
