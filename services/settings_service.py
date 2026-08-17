"""Settings service."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import (
    DEFAULT_OPERATOR_NAME,
    DEFAULT_SATURDAY_RULE,
    DEFAULT_WEEKEND_DAYS,
    SCHEDULING_RULES,
    SCORE_WEIGHTS,
)
from models import Setting


def _get_json(session: Session, key: str, default: Any) -> Any:
    rec = session.scalar(select(Setting).where(Setting.key == key))
    if rec:
        return json.loads(rec.value)
    return default


def _set_json(session: Session, key: str, value: Any) -> None:
    rec = session.scalar(select(Setting).where(Setting.key == key))
    payload = json.dumps(value)
    if rec:
        rec.value = payload
    else:
        session.add(Setting(key=key, value=payload))


def get_scheduling_rules(session: Session) -> dict:
    return _get_json(session, "scheduling_rules", SCHEDULING_RULES.copy())


def get_score_weights(session: Session) -> dict:
    return _get_json(session, "score_weights", SCORE_WEIGHTS.copy())


def get_weekend_days(session: Session) -> list[int]:
    return _get_json(session, "weekend_days", DEFAULT_WEEKEND_DAYS.copy())


def get_saturday_rule(session: Session) -> str:
    return _get_json(session, "saturday_rule", DEFAULT_SATURDAY_RULE)


def get_calendar_settings(session: Session) -> tuple[list[int], str]:
    return get_weekend_days(session), get_saturday_rule(session)


def get_operator_name(session: Session) -> str:
    return _get_json(session, "operator_name", DEFAULT_OPERATOR_NAME)


def set_scheduling_rules(session: Session, rules: dict) -> None:
    _set_json(session, "scheduling_rules", rules)


def set_score_weights(session: Session, weights: dict) -> None:
    _set_json(session, "score_weights", weights)


def set_weekend_days(session: Session, days: list[int]) -> None:
    _set_json(session, "weekend_days", days)


def set_saturday_rule(session: Session, rule: str) -> None:
    _set_json(session, "saturday_rule", rule)


def set_operator_name(session: Session, name: str) -> None:
    _set_json(session, "operator_name", name)


def get_all_settings(session: Session) -> dict:
    return {
        "scheduling_rules": get_scheduling_rules(session),
        "score_weights": get_score_weights(session),
        "weekend_days": get_weekend_days(session),
        "saturday_rule": get_saturday_rule(session),
        "operator_name": get_operator_name(session),
    }
