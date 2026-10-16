"""
End-to-end debug/sanity-check script: group photo in -> attendance marked in
SQLite -> class+subject Excel exported. Not the teacher-facing path (that's
the Streamlit app, which adds a review step) - this auto-commits every
match straight to the DB, so use it for quickly checking recognition
quality, not for real attendance-taking.

Usage:
    python scripts/mark_attendance_from_photo.py <image_path> <phone|smartboard> <class_name> <subject_name> <teacher_username>

Example:
    python scripts/mark_attendance_from_photo.py data/test_photos/phone/group1.jpeg phone "MBA Tech AI A" "Machine Learning" sharma
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from db import get_all_embeddings, get_class_id_by_name, get_subject_id_by_name, get_teacher_id_by_username
from attendance_logger import process_photo
from excel_writer import export_class_subject


def main():
    if len(sys.argv) != 6:
        print(
            "Usage: python mark_attendance_from_photo.py <image_path> <phone|smartboard> "
            "<class_name> <subject_name> <teacher_username>"
        )
        sys.exit(1)

    image_path, source, class_name, subject_name, teacher_username = sys.argv[1:6]
    upsample = 2 if source == "smartboard" else 1

    class_id = get_class_id_by_name(class_name)
    subject_id = get_subject_id_by_name(subject_name)
    teacher_id = get_teacher_id_by_username(teacher_username)
    if class_id is None:
        sys.exit(f"No such class: {class_name!r}")
    if subject_id is None:
        sys.exit(f"No such subject: {subject_name!r}")
    if teacher_id is None:
        sys.exit(f"No such teacher username: {teacher_username!r}")

    enrolled_data = get_all_embeddings(class_id=class_id)
    marked, already_marked, unknown_count = process_photo(
        image_path, source, enrolled_data, class_id, subject_id, teacher_id, upsample=upsample
    )

    print(f"\nNewly marked: {len(marked)}")
    for roll_no, name in marked:
        print(f"  + {name} ({roll_no})")

    print(f"Already marked today: {len(already_marked)}")
    for roll_no, name in already_marked:
        print(f"  = {name} ({roll_no})")

    print(f"Unrecognized faces: {unknown_count}")

    export_class_subject(class_id, subject_id, datetime.now().strftime("%Y-%m-%d"))


if __name__ == "__main__":
    main()
