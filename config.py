"""Default configuration and scheduling rules (overridden by DB settings)."""

from __future__ import annotations

# Role codes
ROLE_NON_EXECUTIVE = "NON_EXECUTIVE"
ROLE_NON_EXECUTIVE_BACKUP = "NON_EXECUTIVE_BACKUP"
ROLE_TRAINEE_ENGINEER = "TRAINEE_ENGINEER"

# Availability statuses that block assignment
BLOCKING_STATUSES = frozenset(
    {"unavailable", "leave", "training", "official_duty", "other"}
)

SCHEDULING_RULES: dict = {
    "backup_preferred_shift": 3,
    "backup_on_first_shift": False,
    "backup_on_second_shift": False,
    "balance_total_duties": True,
    "balance_shift_types": True,
    "balance_non_working_days": True,
    "avoid_consecutive_night_shifts": True,
    "max_consecutive_third_shifts": 2,
    "avoid_double_shift_same_day": True,
    "avoid_third_then_first": True,
    "cross_month_fairness": False,
    "recent_duty_window_days": 7,
    "nw_shortage_trainee_on_primary": True,
    "nw_shortage_ne_on_trainee_slot": True,
}

# Lower score = better candidate. Documented in README.
SCORE_WEIGHTS: dict = {
    "total_duties": 10,
    "same_shift": 8,
    "non_working_day": 5,
    "first_shift": 6,
    "consecutive_third_penalty": 15,
    "third_then_first_penalty": 20,
    "recent_duty": 3,
    "backup_ideal_penalty": 10000,
    "backup_non_third_penalty": 10000,
    "trainee_on_primary_ideal_penalty": 10000,
    "trainee_on_primary_shortage_bonus": -50,
    "backup_nw_third_bonus": -50,
    "trainee_on_trainee_slot_nw_shortage_penalty": 10000,
    "cross_month_shift": 2,
}

DEFAULT_WEEKEND_DAYS: list[int] = [6]  # Sunday always off
DEFAULT_SATURDAY_RULE: str = "first_third_off"  # 1st & 3rd Saturday = holiday; 2nd/4th/5th = working

DEFAULT_SHIFT_TYPES: list[dict] = [
    {"number": 1, "name": "Morning", "start_time": "06:00", "end_time": "14:00"},
    {"number": 2, "name": "Evening", "start_time": "14:00", "end_time": "22:00"},
    {"number": 3, "name": "Night", "start_time": "22:00", "end_time": "06:00"},
]

DEFAULT_OPERATOR_NAME = "DC/In-Charge"
