"""Streamlit session helper."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from database import get_engine, init_db
from models import Base


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Provide a database session for Streamlit pages."""
    init_db()
    engine = get_engine()
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
