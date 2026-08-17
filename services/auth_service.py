"""Authentication and user management."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AuditLog, User


@dataclass
class AuthUser:
    id: int
    username: str
    display_name: str
    role: str
    employee_id: Optional[int]


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == digest


def authenticate(session: Session, username: str, password: str) -> Optional[AuthUser]:
    user = session.scalar(
        select(User).where(User.username == username.strip().lower(), User.active.is_(True))
    )
    if not user or not verify_password(password, user.password_hash):
        return None
    return AuthUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        employee_id=user.employee_id,
    )


def list_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.username)).all())


def create_user(
    session: Session,
    username: str,
    password: str,
    display_name: str,
    role: str,
    employee_id: int | None = None,
    operator: str = "system",
) -> User:
    uname = username.strip().lower()
    if session.scalar(select(User).where(User.username == uname)):
        raise ValueError(f"Username '{uname}' already exists")
    user = User(
        username=uname,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        role=role,
        employee_id=employee_id,
        active=True,
    )
    session.add(user)
    session.flush()
    session.add(
        AuditLog(
            action="user_created",
            entity_type="user",
            entity_id=user.id,
            new_value=uname,
            created_by=operator,
        )
    )
    return user


def delete_user(session: Session, user_id: int, operator: str) -> None:
    user = session.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    if user.username == "dc_incharge":
        raise ValueError("Cannot delete the primary DC/In-Charge account")
    session.add(
        AuditLog(
            action="user_deleted",
            entity_type="user",
            entity_id=user.id,
            old_value=user.username,
            created_by=operator,
        )
    )
    session.delete(user)


def reset_password(session: Session, user_id: int, new_password: str, operator: str) -> None:
    user = session.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    user.password_hash = hash_password(new_password)
    session.add(
        AuditLog(
            action="user_password_reset",
            entity_type="user",
            entity_id=user.id,
            new_value=user.username,
            created_by=operator,
        )
    )
