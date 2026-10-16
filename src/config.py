"""
Central place for paths and tunable constants used across the project.
Change a value once here instead of hunting through every file.
"""

DB_PATH = "data/db/attendance_system.db"
ENROLLMENT_DIR = "data/enrollment"
ATTENDANCE_EXPORTS_DIR = "data/attendance_exports"
OUTPUTS_DIR = "outputs"

MATCH_THRESHOLD = 0.5  # lower = stricter match, higher = looser match

# Faces narrower than this (px) are too small for a reliable embedding, so
# they must match this much more closely to be accepted.
SMALL_FACE_WIDTH = 40
SMALL_FACE_MATCH_THRESHOLD = 0.35
