"""
Wires recognition into attendance marking: photo in, attendance rows
logged out. Built around GROUP photos - every recognized face in the photo
gets its own row in one call; unknown faces are reported but not logged.
Every row is scoped to a specific class + subject + teacher + date.
"""

from datetime import datetime

from db import init_db, mark_attendance
from recognize import recognize_faces


def process_photo(image_path, source, enrolled_data, class_id, subject_id, teacher_id, session_date=None, upsample=1):
    """
    Used by the CLI script (scripts/mark_attendance_from_photo.py) for a quick
    unreviewed test run - auto-commits every match straight to the DB.
    The Streamlit app's Take Attendance tab uses mark_present() below instead,
    after the professor reviews/corrects each face.

    source: a label like "phone" or "smartboard", stored per attendance row
    so you can compute accuracy separately for each, as your eval plan needs.

    Returns: (marked, already_marked, unknown_count)
      marked         - list of (roll_no, name) newly marked this call
      already_marked - list of (roll_no, name) already marked for this class+subject+date
      unknown_count  - number of detected faces that matched no enrolled student
    """
    init_db()
    session_date = session_date or datetime.now().strftime("%Y-%m-%d")
    time_now = datetime.now().strftime("%H:%M:%S")

    results, _ = recognize_faces(image_path, enrolled_data, upsample=upsample)

    marked, already_marked, unknown_count = [], [], 0

    for roll_no, name, _distance in results:
        if roll_no is None:
            unknown_count += 1
            continue

        was_new = mark_attendance(roll_no, name, class_id, subject_id, teacher_id, session_date, time_now, source)
        (marked if was_new else already_marked).append((roll_no, name))

    return marked, already_marked, unknown_count


def mark_present(roll_no, name, source, class_id, subject_id, teacher_id, session_date=None):
    """
    Marks one student present for a class+subject+date. Used by the review
    workflow for both confirmed face matches and manually-added students
    (source="manual"). Returns True if newly marked, False if already marked.
    """
    init_db()
    session_date = session_date or datetime.now().strftime("%Y-%m-%d")
    time_now = datetime.now().strftime("%H:%M:%S")
    return mark_attendance(roll_no, name, class_id, subject_id, teacher_id, session_date, time_now, source)
