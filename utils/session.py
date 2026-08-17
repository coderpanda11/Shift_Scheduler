"""Streamlit session helper."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from database import get_engine, init_db


def _is_streamlit_control_flow(exc: BaseException) -> bool:
    """True for st.rerun() / st.stop() (BaseException, not Exception)."""
    return type(exc).__name__ in ("RerunException", "StopException")


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Provide a database session for Streamlit pages."""
    init_db()
    engine = get_engine()
    session = Session(engine)
    try:
        yield session
        session.commit()
    except BaseException as exc:
        # ponytail: RerunException subclasses BaseException, not Exception
        if _is_streamlit_control_flow(exc):
            session.commit()
        else:
            session.rollback()
        raise
    finally:
        session.close()
