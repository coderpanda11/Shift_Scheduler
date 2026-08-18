"""Roster grid cell labels and NA overlay."""

from datetime import date

from services.schedule_service import _assignment_cell_label, generate_schedule, roster_grid_combined
from tests.conftest import set_unavailable


def test_availability_slot_labels():
    assert _assignment_cell_label(1, "trainee") == "1A"
    assert _assignment_cell_label(2, "trainee") == "2A"
    assert _assignment_cell_label(3, "primary") == "3"


def test_unavailable_non_exec_shows_na(db_session):
    set_unavailable(db_session, "Non-Executive 3", 2026, 9, 10, 12)
    sched = generate_schedule(db_session, 2026, 9, operator="test")
    rows, _, _, _ = roster_grid_combined(db_session, sched)
    ne3 = next(r for r in rows if r["Name"] == "Non-Executive 3")
    assert ne3["10"] == "NA"
    assert ne3["11"] == "NA"
    assert ne3["12"] == "NA"
    ne1 = next(r for r in rows if r["Name"] == "Non-Executive 1")
    assert ne1.get("10") != "NA"


def test_primary_ne_working_off_shows_x(db_session):
    sched = generate_schedule(db_session, 2026, 9, operator="test")
    rows, day_nums, nw_days, _ = roster_grid_combined(db_session, sched)
    ne1 = next(r for r in rows if r["Name"] == "Non-Executive 1")
    trainee = next(r for r in rows if r["Name"] == "Trainee Engineer 1")
    backup = next(r for r in rows if r["Name"] == "Non-Executive Backup")
    working = set(day_nums) - nw_days
    for d in working:
        ne_val = ne1.get(str(d), "")
        if ne_val in ("X", "G"):
            assert ne_val == "X"
        tr_val = trainee.get(str(d), "")
        if tr_val in ("X", "G"):
            assert tr_val == "G"
        bk_val = backup.get(str(d), "")
        if bk_val in ("X", "G"):
            assert bk_val == "G"
