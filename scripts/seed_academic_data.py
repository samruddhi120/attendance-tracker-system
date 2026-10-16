"""
Defines the academic roster - teachers, classes, subjects, who teaches what,
and which existing students belong to which class - and writes it into
SQLite. This is the "admin UI" for this project: edit the data below
whenever the roster changes (new teacher, new class, reassigning a
student, ...), then rerun this script. Every write here is an upsert, so
rerunning after an edit is always safe.

*** EDIT THE VALUES BELOW BEFORE RUNNING - these are placeholders taken
from the feature spec, not a real roster. ***

Usage:
    python scripts/seed_academic_data.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from db import (
    init_db,
    add_teacher,
    add_class,
    add_subject,
    add_class_subject,
    add_teacher_assignment,
    set_student_class,
)

# ---------------------------------------------------------------- Edit this

# (username, password, display name) - the username/password is what the
# teacher types into the app's login screen.
TEACHERS = [
    ("sharma", "changeme123", "Prof. Sharma"),
]

CLASSES = [
    "MBA Tech AI A",
    "MBA Tech AI B",
]

SUBJECTS = [
    "Machine Learning",
    "Artificial Intelligence",
    "Python Programming",
]

# Which subjects exist in which class.
CLASS_SUBJECTS = [
    ("MBA Tech AI A", "Machine Learning"),
    ("MBA Tech AI A", "Artificial Intelligence"),
    ("MBA Tech AI B", "Python Programming"),
]

# Who teaches what: (teacher username, class name, subject name).
TEACHER_ASSIGNMENTS = [
    ("sharma", "MBA Tech AI A", "Machine Learning"),
    ("sharma", "MBA Tech AI A", "Artificial Intelligence"),
    ("sharma", "MBA Tech AI B", "Python Programming"),
]

# Existing enrolled students -> their class, keyed by roll_no. All 11 are in
# MBA Tech AI A for now; move individuals when the real roster is known.
STUDENT_CLASSES = {
    "R003": "MBA Tech AI A",  # Jhilik Biswas
    "R012": "MBA Tech AI A",  # Sachi Jain
    "R016": "MBA Tech AI A",  # Vidisha Kondiniya
    "R023": "MBA Tech AI A",  # Ahmed Moosani
    "R026": "MBA Tech AI A",  # Vedant Pandey
    "R031": "MBA Tech AI A",  # Arnav Rathod
    "R033": "MBA Tech AI A",  # Pratham Sangurdekar
    "R034": "MBA Tech AI A",  # Eshaan Sethi
    "R037": "MBA Tech AI A",  # Riddhima Shah
    "R045": "MBA Tech AI A",  # Priyansh Soni
    "R047": "MBA Tech AI A",  # Mandar Sonkusare
}

# ------------------------------------------------------------------ Seeding


def main():
    init_db()

    teacher_ids = {username: add_teacher(username, password, name) for username, password, name in TEACHERS}
    class_ids = {name: add_class(name) for name in CLASSES}
    subject_ids = {name: add_subject(name) for name in SUBJECTS}

    for class_name, subject_name in CLASS_SUBJECTS:
        add_class_subject(class_ids[class_name], subject_ids[subject_name])

    for username, class_name, subject_name in TEACHER_ASSIGNMENTS:
        add_teacher_assignment(teacher_ids[username], class_ids[class_name], subject_ids[subject_name])

    for roll_no, class_name in STUDENT_CLASSES.items():
        set_student_class(roll_no, class_ids[class_name])

    print(f"Seeded {len(TEACHERS)} teacher(s), {len(CLASSES)} class(es), {len(SUBJECTS)} subject(s).")
    print(f"Assigned {len(STUDENT_CLASSES)} existing student(s) to a class.")


if __name__ == "__main__":
    main()
