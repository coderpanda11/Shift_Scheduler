"""SQLAlchemy ORM models for the shift scheduler."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_backup: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    employees: Mapped[list["Employee"]] = relationship(back_populates="role")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    staff_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    joining_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    leaving_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    availability_pin_hash: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    role: Mapped["Role"] = relationship(back_populates="employees")
    availability: Mapped[list["Availability"]] = relationship(back_populates="employee")


class ShiftType(Base):
    __tablename__ = "shift_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    repeats_yearly: Mapped[bool] = mapped_column(Boolean, default=False)


class DateOverride(Base):
    __tablename__ = "date_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    is_working: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)


class Availability(Base):
    __tablename__ = "availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="availability")


class Schedule(Base):
    __tablename__ = "schedules"
    __table_args__ = (UniqueConstraint("year", "month", "version", name="uq_schedule_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    scheduling_mode: Mapped[str] = mapped_column(String(30), default="ideal")
    explanation_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validation_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quality: Mapped[str] = mapped_column(String(20), default="good")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(100), default="DC/In-Charge")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    assignments: Mapped[list["ShiftAssignment"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )


class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    shift_number: Mapped[int] = mapped_column(Integer, nullable=False)
    slot_kind: Mapped[str] = mapped_column(String(20), nullable=False)  # primary | trainee
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    employee_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    role_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False)

    schedule: Mapped["Schedule"] = relationship(back_populates="assignments")


class ManualOverride(Base):
    __tablename__ = "manual_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id"), nullable=False)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("shift_assignments.id"), nullable=False)
    old_employee_id: Mapped[int] = mapped_column(Integer, nullable=False)
    new_employee_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warnings_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(100), default="DC/In-Charge")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), default="DC/In-Charge")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="staff")  # admin | dc_incharge | staff
    employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VpsMember(Base):
    __tablename__ = "vps_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    staff_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    site: Mapped[str] = mapped_column(String(10), nullable=False)  # dc | dr
    is_tl: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    availability: Mapped[list["VpsAvailability"]] = relationship(back_populates="member")


class VpsAvailability(Base):
    __tablename__ = "vps_availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("vps_members.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    member: Mapped["VpsMember"] = relationship(back_populates="availability")


class VpsSchedule(Base):
    __tablename__ = "vps_schedules"
    __table_args__ = (
        UniqueConstraint("site", "year", "month", "version", name="uq_vps_schedule_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site: Mapped[str] = mapped_column(String(10), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    explanation_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(100), default="DC/In-Charge")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    assignments: Mapped[list["VpsAssignment"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )


class VpsAssignment(Base):
    __tablename__ = "vps_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("vps_schedules.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    shift_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=General, 1-3=shift
    member_id: Mapped[int] = mapped_column(ForeignKey("vps_members.id"), nullable=False)
    member_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    is_carry_over: Mapped[bool] = mapped_column(Boolean, default=False)

    schedule: Mapped["VpsSchedule"] = relationship(back_populates="assignments")
