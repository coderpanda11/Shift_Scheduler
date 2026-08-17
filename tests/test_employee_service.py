"""Employee service tests."""

from models import Employee
from services.employee_service import add_employee, delete_employee, list_roles, update_employee


def test_staff_no_update(db_session):
    roles = list_roles(db_session)
    role_id = roles[0].id
    emp = add_employee(db_session, "Test Person", role_id, staff_no="SAP999", operator="test")
    db_session.commit()
    update_employee(db_session, emp.id, staff_no="SAP1000", operator="test")
    db_session.commit()
    refreshed = db_session.get(Employee, emp.id)
    assert refreshed.staff_no == "SAP1000"


def test_delete_employee_without_schedule(db_session):
    roles = list_roles(db_session)
    emp = add_employee(db_session, "To Delete", roles[0].id, staff_no="DEL001", operator="test")
    db_session.commit()
    eid = emp.id
    delete_employee(db_session, eid, operator="test")
    db_session.commit()
    assert db_session.get(Employee, eid) is None
