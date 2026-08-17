"""Export service tests."""

from services.export_service import export_csv, export_excel, export_print_html
from services.schedule_service import generate_schedule


def test_export_formats(db_session):
    sched = generate_schedule(db_session, 2026, 9)
    db_session.commit()
    csv_data = export_csv(db_session, sched)
    assert b"Name" in csv_data
    xlsx = export_excel(db_session, sched)
    assert len(xlsx) > 100
    html = export_print_html(db_session, sched)
    assert "Duty Roster" in html
    assert "Duty Summary" in html
