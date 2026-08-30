# Attendance System

Face recognition based attendance from group photos (phone or smart-board captured).

## Architecture

- **SQLite** (`data/db/attendance_system.db`) is the source of truth for enrolled
  face embeddings and attendance records.
- **Excel** (`data/attendance_exports/master_attendance.xlsx`) is a generated
  report, exported from SQLite on demand. Nothing writes to Excel directly.
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

## Enrollment

Put student photos in `data/enrollment/<roll_no>_<name>/`, e.g.:

```
data/enrollment/
├── 101_Aditi_Sharma/
│   ├── front.jpg
│   ├── left.jpg
│   └── ... (8 expressions/angles)
├── 102_Rahul_Verma/
└── 103_Sana_Khan/
```

Then, from the project root:

```
python src/enroll.py
```

## Testing detection on one photo

```
python src/detect.py data/test_photos/phone/group1.png
```

Saves a debug image with boxes drawn to `outputs/detected_faces.jpg`.

## Marking attendance from a group photo (end-to-end)

```
python scripts/mark_attendance_from_photo.py data/test_photos/phone/group1.png phone
python scripts/mark_attendance_from_photo.py data/test_photos/smartboard/class1.png smartboard
```

This detects every face in the photo, matches each against enrolled students,
logs attendance to SQLite (de-duplicated per student per day), and exports
today's sheet into the master Excel workbook.

## Module map

| File | Purpose |
|---|---|
| `src/config.py` | Paths and constants used everywhere else |
| `src/db.py` | SQLite schema + read/write helpers |
| `src/detect.py` | Standalone face detection test/debug script |
| `src/enroll.py` | Builds embeddings from `data/enrollment/` into SQLite |
| `src/recognize.py` | Matches detected faces against enrolled embeddings |
| `src/attendance_logger.py` | De-dup + timestamp/source logging to SQLite |
| `src/excel_writer.py` | Exports SQLite attendance into the Excel report |
| `scripts/mark_attendance_from_photo.py` | End-to-end: photo in → Excel out |

## Run order for a fresh machine

1. `pip install -r requirements.txt`
2. Put enrollment photos in `data/enrollment/<roll_no>_<name>/`
3. `python src/enroll.py`
4. `python scripts/mark_attendance_from_photo.py <your_photo> phone`
