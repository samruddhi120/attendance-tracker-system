"""
End-to-end: group photo in -> attendance marked in SQLite -> Excel exported.

Usage:
    python scripts/mark_attendance_from_photo.py <image_path> <phone|smartboard>

Example:
    python scripts/mark_attendance_from_photo.py data/test_photos/phone/group1.png phone
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from db import get_all_embeddings
from attendance_logger import process_photo
from excel_writer import export_day


def main():
    if len(sys.argv) != 3:
        print("Usage: python mark_attendance_from_photo.py <image_path> <phone|smartboard>")
        sys.exit(1)

    image_path, source = sys.argv[1], sys.argv[2]
    upsample = 2 if source == "smartboard" else 1  # wide shots need more upsampling

    enrolled_data = get_all_embeddings()
    marked, already_marked, unknown_count = process_photo(
        image_path, source, enrolled_data, upsample=upsample
    )

    print(f"\nNewly marked: {len(marked)}")
    for roll_no, name in marked:
        print(f"  + {name} ({roll_no})")

    print(f"Already marked today: {len(already_marked)}")
    for roll_no, name in already_marked:
        print(f"  = {name} ({roll_no})")

    print(f"Unrecognized faces: {unknown_count}")

    export_day(datetime.now().strftime("%Y-%m-%d"))


if __name__ == "__main__":
    main()
