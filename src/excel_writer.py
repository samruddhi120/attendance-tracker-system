"""
Exports attendance from SQLite into a per-Class+Subject Excel workbook - one
continuously-updated file per (class, subject) combination, never a new file
per lecture. Layout: one row per student enrolled in that class, one column
per lecture date (P/A), plus trailing Total Present / Total Lectures /
Attendance % columns recomputed from whatever date columns are in the sheet.

SQLite is the source of truth here; this only ever reads the DB and
regenerates the relevant date column, so the DB and the Excel report can
never drift apart or need manual reconciliation. Re-running for a date that
already has a column overwrites that column in place rather than duplicating
it - covers both "attendance already recorded for this date" and two
teachers covering the same class+subject+date.
"""

import os
import re

from openpyxl import Workbook, load_workbook

from config import ATTENDANCE_EXPORTS_DIR
from db import get_attendance_for_session, get_students_by_class, get_class_name, get_subject_name

FIXED_COLUMNS = ["Roll No", "Student Name"]
SUMMARY_COLUMNS = ["Total Present", "Total Lectures", "Attendance %"]


def _safe_filename(name):
    """Turns a class/subject name into a filesystem-safe path segment."""
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def _workbook_path(class_name, subject_name):
    folder = os.path.join(ATTENDANCE_EXPORTS_DIR, _safe_filename(class_name))
    return os.path.join(folder, f"{_safe_filename(subject_name)}.xlsx")


def get_workbook_path(class_id, subject_id):
    """Path of the .xlsx file for this class+subject, for download buttons etc."""
    return _workbook_path(get_class_name(class_id), get_subject_name(subject_id))


def export_class_subject(class_id, subject_id, date):
    """Returns the path of the .xlsx file written/updated."""
    class_name = get_class_name(class_id)
    subject_name = get_subject_name(subject_id)
    workbook_path = _workbook_path(class_name, subject_name)
    os.makedirs(os.path.dirname(workbook_path), exist_ok=True)

    if os.path.exists(workbook_path):
        workbook = load_workbook(workbook_path)
        sheet = workbook.active
    else:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = (_safe_filename(subject_name) or "Attendance")[:31]
        sheet.append(FIXED_COLUMNS + SUMMARY_COLUMNS)

    header = [cell.value for cell in sheet[1]]
    date_columns = [h for h in header if h not in FIXED_COLUMNS and h not in SUMMARY_COLUMNS]

    if date not in date_columns:
        insert_at = len(header) - len(SUMMARY_COLUMNS) + 1  # 1-based, right before summary cols
        sheet.insert_cols(insert_at)
        sheet.cell(row=1, column=insert_at, value=date)
        header = [cell.value for cell in sheet[1]]
        date_columns.append(date)

    present_roll_nos = {row[0] for row in get_attendance_for_session(class_id, subject_id, date)}
    roster = get_students_by_class(class_id)

    date_col_index = header.index(date) + 1
    present_col = header.index("Total Present") + 1
    lectures_col = header.index("Total Lectures") + 1
    pct_col = header.index("Attendance %") + 1
    total_lectures = len(date_columns)

    existing_rows = {
        sheet.cell(row=r, column=1).value: r
        for r in range(2, sheet.max_row + 1)
        if sheet.cell(row=r, column=1).value
    }
    next_row = sheet.max_row + 1

    present_count = 0
    for roll_no, name in roster:
        row_idx = existing_rows.get(roll_no)
        if row_idx is None:
            row_idx = next_row
            next_row += 1
            sheet.cell(row=row_idx, column=1, value=roll_no)
            sheet.cell(row=row_idx, column=2, value=name)
            existing_rows[roll_no] = row_idx

        is_present = roll_no in present_roll_nos
        sheet.cell(row=row_idx, column=date_col_index, value="P" if is_present else "A")
        if is_present:
            present_count += 1

        present_total = sum(
            1 for col_name in date_columns
            if sheet.cell(row=row_idx, column=header.index(col_name) + 1).value == "P"
        )
        sheet.cell(row=row_idx, column=present_col, value=present_total)
        sheet.cell(row=row_idx, column=lectures_col, value=total_lectures)
        pct = round(present_total / total_lectures * 100, 2) if total_lectures else 0
        sheet.cell(row=row_idx, column=pct_col, value=pct)

    workbook.save(workbook_path)
    print(
        f"Exported {len(roster)} student(s) for {class_name} / {subject_name} on {date} "
        f"to {workbook_path} - {present_count} present, {len(roster) - present_count} absent."
    )
    return workbook_path
