"""Export schedule to Excel, CSV, and print-friendly HTML."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from models import Schedule
    from sqlalchemy.orm import Session

from services.schedule_service import (
    duty_summary_rows,
    grid_to_dataframe,
    roster_dataframe_rows,
    roster_grid_combined,
)


def export_csv(session: "Session", sched: "Schedule") -> bytes:
    """Export combined grid roster as CSV bytes."""
    rows, day_nums, _, day_types = roster_grid_combined(session, sched)
    type_row = {"Name": "Day Type", **day_types}
    df = grid_to_dataframe([type_row] + rows, day_nums)
    return df.to_csv(index=False).encode("utf-8")


def export_excel(session: "Session", sched: "Schedule") -> bytes:
    """Export combined roster + duty summary as Excel bytes."""
    rows, day_nums, _, day_types = roster_grid_combined(session, sched)
    type_row = {"Name": "Day Type", **day_types}
    roster = grid_to_dataframe([type_row] + rows, day_nums)
    summary = pd.DataFrame(duty_summary_rows(session, sched))
    detail = pd.DataFrame(roster_dataframe_rows(session, sched))

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        roster.to_excel(writer, sheet_name="Duty Roster", index=False)
        summary.to_excel(writer, sheet_name="Duty Summary", index=False)
        detail.to_excel(writer, sheet_name="Day Detail", index=False)
    buf.seek(0)
    return buf.read()


def export_print_html(session: "Session", sched: "Schedule") -> str:
    """Print-friendly HTML combined grid roster."""
    rows, day_nums, nw_days, day_types = roster_grid_combined(session, sched)
    summary = duty_summary_rows(session, sched)
    title = f"Duty Roster — {sched.month:02d}/{sched.year} (v{sched.version})"
    cols = ["Name"] + [str(d) for d in day_nums]

    html = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{title}</title>",
        "<style>",
        "body{font-family:Arial,sans-serif;margin:24px;}",
        "h1,h2{font-size:16px;} table{border-collapse:collapse;width:100%;margin-top:12px;}",
        "th,td{border:1px solid #ccc;padding:4px 6px;font-size:11px;text-align:center;}",
        "th{background:#f1f5f9;}.name{text-align:left;font-weight:600;}.nw{background:#fef3c7;}.hdr{background:#e2e8f0;font-weight:600;}",
        "@media print{body{margin:12px;}}",
        "</style></head><body>",
        f"<h1>{title}</h1>",
        "<p>G = General · 1/2/3 = primary shifts · 1t/2t = trainee companion slots</p>",
        "<h2>Duty Roster</h2><table><tr>",
    ]
    for col in cols:
        html.append(f"<th>{col}</th>")
    html.append("</tr><tr>")
    html.append('<td class="name hdr">Day Type</td>')
    for d in day_nums:
        cls = ' class="nw hdr"' if d in nw_days else ' class="hdr"'
        html.append(f"<td{cls}>{day_types.get(str(d), '')}</td>")
    html.append("</tr>")
    for row in rows:
        html.append("<tr>")
        html.append(f'<td class="name">{row["Name"]}</td>')
        for d in day_nums:
            cls = ' class="nw"' if d in nw_days else ""
            html.append(f"<td{cls}>{row.get(str(d), '')}</td>")
        html.append("</tr>")
    html.append("</table><h2>Duty Summary</h2><table><tr>")
    if summary:
        for col in summary[0]:
            html.append(f"<th>{col}</th>")
        html.append("</tr>")
        for row in summary:
            html.append("<tr>")
            for v in row.values():
                html.append(f"<td>{v}</td>")
            html.append("</tr>")
    html.append("</body></html>")
    return "".join(html)
