"""Database initialization tests."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_engine, init_db
from models import Employee, Role, ShiftType


def test_init_db_seeds_data():
    engine = get_engine("sqlite:///:memory:")
    init_db("sqlite:///:memory:", engine=engine)
    with Session(engine) as session:
        roles = list(session.scalars(select(Role)).all())
        assert len(roles) == 3
        employees = list(session.scalars(select(Employee)).all())
        assert len(employees) == 8
        shifts = list(session.scalars(select(ShiftType)).all())
        assert len(shifts) == 3
