"""Scheduling engine test scenarios (spec §32)."""

from __future__ import annotations

from datetime import date

import pytest

from config import ROLE_NON_EXECUTIVE, ROLE_NON_EXECUTIVE_BACKUP, ROLE_TRAINEE_ENGINEER
from scheduler.engine import ScheduleEngine
from tests.conftest import build_test_context, set_unavailable


class TestScenarioIdeal:
    """Scenario 1: 3 NE, 1 Backup, 4 Trainees all available."""

    def test_ideal_mode(self, db_session, engine_instance):
        ctx = build_test_context(db_session, 2026, 9)
        result = engine_instance.generate_schedule(ctx)
        assert result.mode == "ideal"
        assert result.validation.quality in ("good", "warning")
        assert not result.validation.conflicts

    def test_backup_mostly_unused(self, db_session, engine_instance):
        ctx = build_test_context(db_session, 2026, 9)
        result = engine_instance.generate_schedule(ctx)
        backup_duties = [
            a for a in result.assignments if a.role_code == ROLE_NON_EXECUTIVE_BACKUP
        ]
        assert len(backup_duties) == 0

    def test_ne_fairness(self, db_session, engine_instance):
        ctx = build_test_context(db_session, 2026, 9)
        result = engine_instance.generate_schedule(ctx)
        ne_ids = [
            e.id for e in ctx.employees if e.role_code == ROLE_NON_EXECUTIVE
        ]
        totals = {}
        for a in result.assignments:
            if a.employee_id in ne_ids:
                totals[a.employee_id] = totals.get(a.employee_id, 0) + 1
        if totals:
            assert max(totals.values()) - min(totals.values()) <= 1

    def test_trainee_fairness(self, db_session, engine_instance):
        ctx = build_test_context(db_session, 2026, 9)
        result = engine_instance.generate_schedule(ctx)
        tr_ids = [
            e.id for e in ctx.employees if e.role_code == ROLE_TRAINEE_ENGINEER
        ]
        totals = {}
        for a in result.assignments:
            if a.slot_kind == "trainee" and a.employee_id in tr_ids:
                totals[a.employee_id] = totals.get(a.employee_id, 0) + 1
        if totals:
            assert max(totals.values()) - min(totals.values()) <= 1


class TestScenarioOneNEUnavailable:
    """Scenario 2: One primary NE unavailable."""

    def test_backup_mode(self, db_session, engine_instance):
        set_unavailable(db_session, "Non-Executive 3", 2026, 9, 1, 30)
        ctx = build_test_context(db_session, 2026, 9)
        result = engine_instance.generate_schedule(ctx)
        assert result.mode == "backup_rebalanced"

    def test_backup_used_on_third(self, db_session, engine_instance):
        set_unavailable(db_session, "Non-Executive 3", 2026, 9, 1, 30)
        ctx = build_test_context(db_session, 2026, 9)
        result = engine_instance.generate_schedule(ctx)
        backup_thirds = [
            a
            for a in result.assignments
            if a.role_code == ROLE_NON_EXECUTIVE_BACKUP and a.shift_number == 3
        ]
        assert len(backup_thirds) > 0

    def test_no_assign_during_unavailable(self, db_session, engine_instance):
        set_unavailable(db_session, "Non-Executive 3", 2026, 9, 12, 17)
        ctx = build_test_context(db_session, 2026, 9)
        result = engine_instance.generate_schedule(ctx)
        ne3 = next(e for e in ctx.employees if e.name == "Non-Executive 3")
        for a in result.assignments:
            if a.employee_id == ne3.id:
                assert not (date(2026, 9, 12) <= a.date <= date(2026, 9, 17))


class TestMonthLengths:
    """Scenarios 4-6: 30, 31, February days."""

    @pytest.mark.parametrize("year,month", [(2026, 4), (2026, 1), (2026, 2), (2024, 2)])
    def test_generates_without_conflict(self, db_session, engine_instance, year, month):
        ctx = build_test_context(db_session, year, month)
        result = engine_instance.generate_schedule(ctx)
        assert result.validation.quality != "conflict" or len(result.vacant_slots) == 0


class TestHolidays:
    """Scenario 7: Several holidays."""

    def test_nwd_first_shift_fairness(self, db_session, engine_instance):
        from models import Holiday

        for d in [5, 12, 19, 26]:
            db_session.add(Holiday(date=date(2026, 9, d), name=f"Holiday {d}", repeats_yearly=False))
        db_session.commit()
        ctx = build_test_context(db_session, 2026, 9)
        ctx.holidays = [(date(2026, 9, d), False) for d in [5, 12, 19, 26]]
        result = engine_instance.generate_schedule(ctx)
        ne_ids = [e.id for e in ctx.employees if e.role_code == ROLE_NON_EXECUTIVE]
        first_counts = {eid: 0 for eid in ne_ids}
        for a in result.assignments:
            if a.shift_number == 1 and a.slot_kind == "primary" and a.employee_id in ne_ids:
                first_counts[a.employee_id] += 1
        if first_counts:
            assert max(first_counts.values()) - min(first_counts.values()) <= 1


class TestVersioning:
    """Scenario 9: Regeneration keeps old version."""

    def test_new_version_on_regenerate(self, db_session):
        from services.schedule_service import generate_schedule, list_schedules

        s1 = generate_schedule(db_session, 2026, 9)
        db_session.commit()
        s2 = generate_schedule(db_session, 2026, 9)
        db_session.commit()
        assert s2.version == s1.version + 1
        all_s = list_schedules(db_session, 2026, 9)
        assert len(all_s) == 2


class TestManualOverride:
    """Scenario 8: Manual override audit."""

    def test_override_audit(self, db_session):
        from models import AuditLog, Employee
        from services.schedule_service import generate_schedule, manual_override_assignment
        from sqlalchemy import select

        sched = generate_schedule(db_session, 2026, 9)
        db_session.commit()
        assignment = sched.assignments[0]
        # Find an employee not already assigned on that date
        busy = {
            a.employee_id
            for a in sched.assignments
            if a.date == assignment.date
        }
        new_emp = db_session.scalar(
            select(Employee).where(
                Employee.active.is_(True),
                Employee.id.not_in(busy),
                Employee.id != assignment.employee_id,
            )
        )
        assert new_emp is not None
        manual_override_assignment(
            db_session,
            sched.id,
            assignment.id,
            new_emp.id,
            reason="test override",
            confirm_warnings=True,
        )
        db_session.commit()
        logs = list(db_session.scalars(select(AuditLog).where(AuditLog.action == "manual_override")))
        assert len(logs) >= 1


class TestTraineeUnavailable:
    """Scenario 10: Trainee unavailable."""

    def test_trainee_rebalance(self, db_session, engine_instance):
        set_unavailable(db_session, "Trainee Engineer 4", 2026, 9, 1, 30)
        ctx = build_test_context(db_session, 2026, 9)
        result = engine_instance.generate_schedule(ctx)
        tr4 = next(e for e in ctx.employees if e.name == "Trainee Engineer 4")
        trainee_assigns = [
            a for a in result.assignments if a.slot_kind == "trainee" and a.employee_id == tr4.id
        ]
        assert len(trainee_assigns) == 0
        tr_ids = [e.id for e in ctx.employees if e.role_code == ROLE_TRAINEE_ENGINEER and e.id != tr4.id]
        totals = {}
        for a in result.assignments:
            if a.slot_kind == "trainee" and a.employee_id in tr_ids:
                totals[a.employee_id] = totals.get(a.employee_id, 0) + 1
        if totals:
            assert max(totals.values()) - min(totals.values()) <= 1
