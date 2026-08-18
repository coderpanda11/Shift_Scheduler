"""Database engine, session management, initialization, and seed data."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from config import (
    DEFAULT_OPERATOR_NAME,
    DEFAULT_SATURDAY_RULE,
    DEFAULT_SHIFT_TYPES,
    DEFAULT_WEEKEND_DAYS,
    ROLE_NON_EXECUTIVE,
    ROLE_NON_EXECUTIVE_BACKUP,
    ROLE_PROJECT_ENGINEER,
    ROLE_TRAINEE_ENGINEER,
    SCHEDULING_RULES,
    SCORE_WEIGHTS,
    VPS_SITE_DC,
    VPS_SITE_DR,
    default_availability_pin,
)
from models import Base, Employee, Role, Setting, ShiftType, User, VpsMember
from services.auth_service import hash_password

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "scheduler.db"
DEFAULT_DB_URL = f"sqlite:///{DB_PATH}"


def get_engine(db_url: str | None = None):
    """Create SQLAlchemy engine."""
    url = db_url or DEFAULT_DB_URL
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    kwargs: dict = {"connect_args": connect_args}
    # ponytail: StaticPool keeps one shared in-memory DB for tests
    if url in ("sqlite:///:memory:", "sqlite://"):
        kwargs["poolclass"] = StaticPool
        url = "sqlite://"
    return create_engine(url, **kwargs)


def get_session_factory(db_url: str | None = None) -> sessionmaker[Session]:
    engine = get_engine(db_url)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_session(db_url: str | None = None) -> Generator[Session, None, None]:
    """Context-style session generator."""
    factory = get_session_factory(db_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(db_url: str | None = None, engine=None) -> None:
    """Create tables and seed if empty."""
    if db_url is None and engine is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    eng = engine or get_engine(db_url)
    Base.metadata.create_all(eng)
    _migrate_schema(eng)
    with Session(eng) as session:
        if session.scalar(select(Role).limit(1)) is None:
            _seed(session)
            session.commit()
        else:
            _seed_users_if_empty(session)
            _ensure_calendar_settings(session)
            _link_default_staff_user(session)
            _ensure_vps_members(session)
            _ensure_extra_roles(session)
            _sync_employees_from_seed(session)
            _sync_vps_members_from_seed(session)
            _ensure_employee_availability_pins(session)
            session.commit()


def _migrate_schema(engine) -> None:
    """Add new columns to existing SQLite databases."""
    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(employees)")).fetchall()
        cols = {row[1] for row in rows}
        if "staff_no" not in cols:
            conn.execute(text("ALTER TABLE employees ADD COLUMN staff_no VARCHAR(50)"))
            conn.commit()
        rows = conn.execute(text("PRAGMA table_info(employees)")).fetchall()
        cols = {row[1] for row in rows}
        if "availability_pin_hash" not in cols:
            conn.execute(
                text("ALTER TABLE employees ADD COLUMN availability_pin_hash VARCHAR(200)")
            )
            conn.commit()


def _seed(session: Session) -> None:
    """Seed roles, shift types, settings, and placeholder employees."""
    roles = [
        Role(code=ROLE_NON_EXECUTIVE, name="Non-Executive", is_backup=False, sort_order=1),
        Role(code=ROLE_NON_EXECUTIVE_BACKUP, name="Non-Executive Backup", is_backup=True, sort_order=2),
        Role(code=ROLE_TRAINEE_ENGINEER, name="Trainee Engineer", is_backup=False, sort_order=3),
        Role(code=ROLE_PROJECT_ENGINEER, name="Project Engineer", is_backup=False, sort_order=4),
    ]
    session.add_all(roles)
    session.flush()

    role_map = {r.code: r.id for r in roles}

    for st in DEFAULT_SHIFT_TYPES:
        start = time.fromisoformat(st["start_time"]) if st.get("start_time") else None
        end = time.fromisoformat(st["end_time"]) if st.get("end_time") else None
        session.add(
            ShiftType(
                number=st["number"],
                name=st["name"],
                start_time=start,
                end_time=end,
                active=True,
            )
        )

    settings = {
        "scheduling_rules": SCHEDULING_RULES,
        "score_weights": SCORE_WEIGHTS,
        "weekend_days": DEFAULT_WEEKEND_DAYS,
        "saturday_rule": DEFAULT_SATURDAY_RULE,
        "operator_name": DEFAULT_OPERATOR_NAME,
    }
    for key, value in settings.items():
        session.add(Setting(key=key, value=json.dumps(value)))

    for name, staff_no, role_code in EMPLOYEE_SEED:
        session.add(
            Employee(
                name=name,
                staff_no=staff_no,
                role_id=role_map[role_code],
                active=True,
                availability_pin_hash=hash_password(default_availability_pin(staff_no)),
            )
        )

    _seed_users_if_empty(session)
    _link_default_staff_user(session)
    _seed_vps_members(session)


# ponytail: edit names/IDs here; existing DBs sync on app start via _sync_* helpers
EMPLOYEE_SEED: list[tuple[str, str, str]] = [
    ("Non-Executive 1", "NE001", ROLE_NON_EXECUTIVE),
    ("Non-Executive 2", "NE002", ROLE_NON_EXECUTIVE),
    ("Non-Executive 3", "NE003", ROLE_NON_EXECUTIVE),
    ("Non-Executive Backup", "NE004", ROLE_NON_EXECUTIVE_BACKUP),
    ("Trainee Engineer 1", "TE001", ROLE_TRAINEE_ENGINEER),
    ("Trainee Engineer 2", "TE002", ROLE_TRAINEE_ENGINEER),
    ("Trainee Engineer 3", "TE003", ROLE_TRAINEE_ENGINEER),
    ("Trainee Engineer 4", "TE004", ROLE_TRAINEE_ENGINEER),
    ("Project Engineer", "PE001", ROLE_PROJECT_ENGINEER),
]

VPS_MEMBER_SEED: list[tuple[str, str, str, bool, int]] = [
    # site, name, staff_no, is_tl, sort_order
    (VPS_SITE_DC, "VPS TL", "VPS-TL", True, 1),
    (VPS_SITE_DC, "Nitin", "VPS-DC1", False, 2),
    (VPS_SITE_DC, "VPS DC Member 2", "VPS-DC2", False, 3),
    (VPS_SITE_DC, "VPS DC Member 3", "VPS-DC3", False, 4),
    (VPS_SITE_DR, "VPS DR Member 1", "VPS-DR1", False, 1),
    (VPS_SITE_DR, "VPS DR Member 2", "VPS-DR2", False, 2),
    (VPS_SITE_DR, "VPS DR Member 3", "VPS-DR3", False, 3),
    (VPS_SITE_DR, "VPS DR Member 4", "VPS-DR4", False, 4),
]


def _seed_vps_members(session: Session) -> None:
    if session.scalar(select(VpsMember).limit(1)) is not None:
        return
    for site, name, staff_no, is_tl, order in VPS_MEMBER_SEED:
        session.add(
            VpsMember(
                name=name,
                staff_no=staff_no,
                site=site,
                is_tl=is_tl,
                sort_order=order,
                active=True,
            )
        )


def _sync_employees_from_seed(session: Session) -> None:
    """Apply name/role updates from EMPLOYEE_SEED to existing rows (matched by staff_no)."""
    role_map = {r.code: r.id for r in session.scalars(select(Role)).all()}
    for name, staff_no, role_code in EMPLOYEE_SEED:
        role_id = role_map.get(role_code)
        if not role_id:
            continue
        emp = session.scalar(select(Employee).where(Employee.staff_no == staff_no))
        if emp:
            emp.name = name
            emp.role_id = role_id


def _sync_vps_members_from_seed(session: Session) -> None:
    """Apply name/site/TL updates from VPS_MEMBER_SEED (matched by staff_no); add if missing."""
    for site, name, staff_no, is_tl, order in VPS_MEMBER_SEED:
        member = session.scalar(select(VpsMember).where(VpsMember.staff_no == staff_no))
        if member:
            member.name = name
            member.site = site
            member.is_tl = is_tl
            member.sort_order = order
        else:
            session.add(
                VpsMember(
                    name=name,
                    staff_no=staff_no,
                    site=site,
                    is_tl=is_tl,
                    sort_order=order,
                    active=True,
                )
            )


def _ensure_extra_roles(session: Session) -> None:
    """Add roles introduced after initial deploy (existing DBs skip _seed)."""
    extras = [
        (ROLE_PROJECT_ENGINEER, "Project Engineer", False, 4),
    ]
    for code, name, is_backup, sort_order in extras:
        if session.scalar(select(Role).where(Role.code == code)) is None:
            session.add(
                Role(code=code, name=name, is_backup=is_backup, sort_order=sort_order)
            )


def _ensure_vps_members(session: Session) -> None:
    _seed_vps_members(session)
    _sync_vps_members_from_seed(session)


def _seed_users_if_empty(session: Session) -> None:
    if session.scalar(select(User).limit(1)) is not None:
        return
    defaults = [
        ("dc_incharge", "DcIncharge@123", "DC / In-Charge", "admin"),
        ("scheduler1", "Scheduler@123", "Scheduler User 1", "dc_incharge"),
        ("staff_view", "Staff@123", "Staff Viewer", "staff"),
        ("staff_view2", "Staff@123", "Staff Viewer 2", "staff"),
    ]
    for username, password, display, role in defaults:
        session.add(
            User(
                username=username,
                password_hash=hash_password(password),
                display_name=display,
                role=role,
                active=True,
            )
        )


def _link_default_staff_user(session: Session) -> None:
    """Link demo staff login to Trainee Engineer 1 for My Schedule / My Availability."""
    staff = session.scalar(select(User).where(User.username == "staff_view"))
    if not staff or staff.employee_id is not None:
        return
    emp = session.scalar(select(Employee).where(Employee.staff_no == "TE001"))
    if emp:
        staff.employee_id = emp.id


def _ensure_employee_availability_pins(session: Session) -> None:
    """Set default per-employee PIN where missing (matched by staff_no)."""
    for _name, staff_no, _role in EMPLOYEE_SEED:
        emp = session.scalar(select(Employee).where(Employee.staff_no == staff_no))
        if emp and not emp.availability_pin_hash:
            emp.availability_pin_hash = hash_password(default_availability_pin(staff_no))


def _ensure_calendar_settings(session: Session) -> None:
    """Add calendar settings on existing DBs."""
    if session.scalar(select(Setting).where(Setting.key == "saturday_rule")) is None:
        session.add(Setting(key="saturday_rule", value=json.dumps(DEFAULT_SATURDAY_RULE)))
    # ponytail: migrate old all-Saturday-off to Sunday + 1st/3rd Sat rule
    wk = session.scalar(select(Setting).where(Setting.key == "weekend_days"))
    if wk and "[5, 6]" in wk.value:
        wk.value = json.dumps(DEFAULT_WEEKEND_DAYS)
