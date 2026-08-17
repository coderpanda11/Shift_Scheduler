"""Shared roster grid display helpers."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services.schedule_service import grid_to_dataframe


def _style_combined_grid(df: pd.DataFrame, nw_days: set[int]):
    """Style day-type row + employee rows in one table."""
    styles = pd.DataFrame("", index=df.index, columns=df.columns)

    for idx, row in df.iterrows():
        is_day_type = row.get("Name") == "Day Type"
        if is_day_type:
            styles.loc[idx, "Name"] = "background-color: #e2e8f0; font-weight: 700"
            for col in styles.columns:
                if col == "Name":
                    continue
                if col in {str(d) for d in nw_days}:
                    styles.loc[idx, col] = "background-color: #fef3c7; font-weight: 600"
                else:
                    styles.loc[idx, col] = "background-color: #e2e8f0; font-weight: 600"
        else:
            styles.loc[idx, "Name"] = "font-weight: 600; background-color: #f8fafc"
            for col in styles.columns:
                if col == "Name":
                    continue
                val = str(row.get(col, ""))
                if col in {str(d) for d in nw_days}:
                    styles.loc[idx, col] = "background-color: #fef3c7"
                elif val == "G":
                    styles.loc[idx, col] = "background-color: #dcfce7; color: #166534"

    return df.style.apply(lambda _: styles, axis=None)


def render_combined_roster(
    rows: list[dict],
    day_nums: list[int],
    nw_days: set[int],
    day_types: dict[str, str],
    title: str = "Monthly Duty Roster",
) -> None:
    """Render one combined table: day-type row + all employees."""
    st.subheader(title)
    st.caption(
        "**G** = General (working day, no shift duty) · "
        "**1 / 2 / 3** = 1st / 2nd / 3rd shift (primary) · "
        "**1t / 2t** = trainee companion on 1st / 2nd · blank = off (NW day)"
    )

    type_row = {"Name": "Day Type", **{str(d): day_types.get(str(d), "") for d in day_nums}}
    all_rows = [type_row] + rows
    df = grid_to_dataframe(all_rows, day_nums)

    if len(df) <= 1:
        st.info("No assignments to display.")
        return

    st.dataframe(_style_combined_grid(df, nw_days), use_container_width=True, hide_index=True)
