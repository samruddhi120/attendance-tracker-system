# Attendance System

Face recognition based attendance from group photos (phone or smart-board captured).

## Architecture

- **SQLite** (`data/db/attendance_system.db`) is the source of truth for the
  academic structure (teachers, classes, subjects, who teaches what),
  enrolled students and face embeddings, and attendance records.
- **Excel**: one continuously-updated `.xlsx` per Class+Subject under
  `data/attendance_exports/<class>/<subject>.xlsx`, generated from SQLite on
  demand. Nothing writes to Excel directly.
- A teacher logs in (username/password) and only sees the classes/subjects
  assigned to them; attendance is always scoped to one Class+Subject+Date.
- `src/config.py` holds every path and tunable constant - change it once there,
  not across multiple files.

## Setup

```
pip install -r requirements.txt
```

`face_recognition` depends on `dlib`, which needs CMake + a C++ compiler to build.
If `pip install` fails on dlib specifically, install it via conda instead:
```
conda install -c conda-forge dlib
pip install face_recognition
```

**Windows without conda/Visual Studio:** if you have no CMake or C++ build tools
installed, dlib can't compile from source. Use the prebuilt `dlib-bin` wheel
instead:
```
pip install dlib-bin
pip install --no-deps face_recognition face_recognition_models
pip install opencv-python openpyxl numpy pandas streamlit "setuptools<81"
```
(`--no-deps` is needed because pip's dependency resolver looks for a package
literally named `dlib`, not `dlib-bin`, and would otherwise try to build it
from source anyway.)

**Note:** don't create `venv/` inside a OneDrive-synced folder if you'll ever
open the project on another machine - a venv hardcodes absolute paths to the
Python interpreter it was created with, so a synced copy breaks on any other
machine. Recreate the venv locally instead (`python -m venv venv`) if that happens.

## Academic setup (teachers, classes, subjects)

Before anyone can log in or take attendance, the roster needs to exist.
Edit the placeholder data at the top of `scripts/seed_academic_data.py`
(teachers + login credentials, classes, subjects, which subjects belong to
which class, who teaches what, and which class each student is in), then:

```
python scripts/seed_academic_data.py
```

Rerun it any time the roster changes - every write is an upsert, so it's
always safe to run again after editing.

## Enrollment

Student photos still live in `data/enrollment/<roll_no>_<name>/`, e.g.:

```
data/enrollment/
├── 101_Aditi_Sharma/
│   ├── front.jpg
│   ├── left.jpg
│   └── ... (8 expressions/angles)
├── 102_Rahul_Verma/
└── 103_Sana_Khan/
```

The primary way to enroll a student is the **Enroll Student** tab in the
Streamlit app now, since it lets you assign their class at the same time.
`python src/enroll.py` still works as a CLI batch path for the folders
above, but it has no class information - a student enrolled this way needs
their class set separately (via `scripts/seed_academic_data.py`'s
`STUDENT_CLASSES`, or the Enroll tab won't re-enroll but re-running the
script will still be needed to link them to a class).

## Testing detection on one photo

```
python src/detect.py data/test_photos/phone/group1.png
```

Saves a debug image with boxes drawn to `outputs/detected_faces.jpg`.

## Marking attendance from a group photo (end-to-end debug path)

```
python scripts/mark_attendance_from_photo.py data/test_photos/phone/group1.jpeg phone "MBA Tech AI A" "Machine Learning" sharma
```

This detects every face in the photo, matches each against that class's
enrolled students, logs attendance to SQLite (de-duplicated per student per
class+subject+day), and exports that class+subject's Excel workbook. It
auto-commits every match with no review step - the Streamlit app's Take
Attendance tab is the real teacher-facing path.

## Module map

| File | Purpose |
|---|---|
| `src/config.py` | Paths and constants used everywhere else |
| `src/db.py` | SQLite schema + read/write helpers, including teachers/classes/subjects and password hashing |
| `src/detect.py` | Standalone face detection test/debug script |
| `src/enroll.py` | Builds embeddings from `data/enrollment/` into SQLite |
| `src/recognize.py` | Matches detected faces against enrolled embeddings |
| `src/attendance_logger.py` | De-dup + timestamp/source logging to SQLite, scoped to class+subject |
| `src/excel_writer.py` | Exports SQLite attendance into one workbook per class+subject |
| `scripts/seed_academic_data.py` | Defines/updates teachers, classes, subjects, and assignments |
| `scripts/mark_attendance_from_photo.py` | End-to-end debug path: photo in → Excel out, no review step |

## Run order for a fresh machine

1. `pip install -r requirements.txt`
2. Edit and run `python scripts/seed_academic_data.py`
3. Put enrollment photos in `data/enrollment/<roll_no>_<name>/`, then either
   `python src/enroll.py` or use the Enroll Student tab in the app
4. `streamlit run app.py`, log in as one of the seeded teachers
