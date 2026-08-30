"""
Enrollment: reads photos from data/enrollment/<roll_no>_<name>/*.jpg
and writes embeddings into SQLite.

Folder naming convention: "<roll_no>_<name>", e.g. "101_Aditi_Sharma".
Your 3 enrolled students' folders need to follow this pattern - the
roll_no is what the database and the final Excel report key on.
"""

import os

import face_recognition

from config import ENROLLMENT_DIR
from db import init_db, add_student, add_embedding


def parse_folder_name(folder_name):
    roll_no, _, name = folder_name.partition("_")
    if not name:
        raise ValueError(
            f"Folder '{folder_name}' doesn't match '<roll_no>_<name>'. "
            "Rename it, e.g. '101_Aditi_Sharma'."
        )
    return roll_no, name.replace("_", " ")


def enroll_student(roll_no, name, folder_path):
    """
    Processes every photo in folder_path for one student and saves their
    embeddings to SQLite. Returns the number of photos successfully enrolled.

    Pulled out as its own function so both the CLI batch run below and the
    Streamlit "Enroll Student" tab can call the same logic on one student
    at a time, instead of duplicating it.
    """
    add_student(roll_no, name)

    photos_enrolled = 0
    for photo_name in os.listdir(folder_path):
        photo_path = os.path.join(folder_path, photo_name)
        image = face_recognition.load_image_file(photo_path)
        face_encodings = face_recognition.face_encodings(image)

        if len(face_encodings) == 0:
            print(f"Warning: no face found in {photo_path}, skipping.")
            continue
        if len(face_encodings) > 1:
            print(f"Warning: multiple faces in {photo_path}, using the first one.")

        add_embedding(roll_no, face_encodings[0], source_photo=photo_name)
        photos_enrolled += 1

    return photos_enrolled


def build_embeddings():
    """Batch-enrolls every student folder under data/enrollment/. CLI entry point."""
    init_db()
    total_students, total_photos = 0, 0

    for folder_name in os.listdir(ENROLLMENT_DIR):
        folder_path = os.path.join(ENROLLMENT_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue

        roll_no, name = parse_folder_name(folder_name)
        photos_enrolled = enroll_student(roll_no, name, folder_path)

        if photos_enrolled:
            print(f"Enrolled {name} ({roll_no}): {photos_enrolled} photo(s) processed.")
            total_students += 1
            total_photos += photos_enrolled
        else:
            print(f"Warning: no usable photos for {folder_name}, skipping.")

    print(f"\nDone. {total_students} student(s), {total_photos} embedding(s) saved to SQLite.")


if __name__ == "__main__":
    build_embeddings()
