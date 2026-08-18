"""Availability PIN auth tests."""

from config import (
    ROLE_NON_EXECUTIVE,
    ROLE_PROJECT_ENGINEER,
    ROLE_TRAINEE_ENGINEER,
    default_availability_pin,
)
from models import Employee
from services.availability_auth_service import (
    employee_requires_avail_pin,
    verify_employee_availability_pin,
)
from services.employee_service import set_employee_availability_pin


def test_employee_requires_avail_pin():
    assert employee_requires_avail_pin(ROLE_NON_EXECUTIVE)
    assert employee_requires_avail_pin(ROLE_TRAINEE_ENGINEER)
    assert employee_requires_avail_pin(ROLE_PROJECT_ENGINEER)
    assert not employee_requires_avail_pin("dc_incharge")


def test_verify_employee_availability_pin(db_session):
    emp = db_session.query(Employee).filter(Employee.staff_no == "TE001").one()
    assert verify_employee_availability_pin(
        db_session, emp.id, default_availability_pin("TE001")
    )
    assert not verify_employee_availability_pin(db_session, emp.id, "wrong")


def test_ne_pins_are_independent(db_session):
    """Each NE has their own PIN — NE001's code must not unlock NE002."""
    ne1 = db_session.query(Employee).filter(Employee.staff_no == "NE001").one()
    ne2 = db_session.query(Employee).filter(Employee.staff_no == "NE002").one()
    assert verify_employee_availability_pin(
        db_session, ne1.id, default_availability_pin("NE001")
    )
    assert not verify_employee_availability_pin(
        db_session, ne2.id, default_availability_pin("NE001")
    )


def test_reset_employee_pin(db_session):
    emp = db_session.query(Employee).filter(Employee.staff_no == "TE002").one()
    set_employee_availability_pin(db_session, emp.id, "CustomPin@TE002")
    db_session.commit()
    assert verify_employee_availability_pin(db_session, emp.id, "CustomPin@TE002")
    assert not verify_employee_availability_pin(
        db_session, emp.id, default_availability_pin("TE002")
    )
