"""Pytest fixtures for shift scheduler tests."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import get_engine, init_db
from models import Availability, Employee
from scheduler.calendar_util import month_dates
from scheduler.engine import ScheduleContext, ScheduleEngine
from scheduler.fairness import EmployeeInfo
from services.employee_service import employees_by_role_code, list_employees
from config import ROLE_NON_EXECUTIVE, ROLE_NON_EXECUTIVE_BACKUP, ROLE_TRAINEE_ENGINEER


@pytest.fixture
def db_session():
    db_url = "sqlite:///:memory:"
    engine = get_engine(db_url)
    init_db(db_url, engine=engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def engine_instance():
    return ScheduleEngine()


def build_test_context(session: Session, year: int, month: int) -> ScheduleContext:
    from services.availability_service import build_availability_map
    from services.settings_service import get_calendar_settings, get_scheduling_rules, get_score_weights

    emps = [
        EmployeeInfo(id=e.id, name=e.name, role_code=e.role.code, active=e.active)
        for e in list_employees(session, active_only=True)
    ]
    weekend_days, saturday_rule = get_calendar_settings(session)
    return ScheduleContext(
        year=year,
        month=month,
        employees=emps,
        availability_map=build_availability_map(session, year, month),
        weekend_days=weekend_days,
        saturday_rule=saturday_rule,
        holidays=[],
        date_overrides={},
        rules=get_scheduling_rules(session),
        weights=get_score_weights(session),
    )


def set_unavailable(session: Session, employee_name: str, year: int, month: int, start_day: int, end_day: int):
    emp = session.query(Employee).filter(Employee.name == employee_name).one()
    from datetime import date
    session.add(
        Availability(
            employee_id=emp.id,
            start_date=date(year, month, start_day),
            end_date=date(year, month, end_day),
            status="leave",
            reason="test",
        )
    )
    session.commit()
