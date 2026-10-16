"""
SQLite storage layer for the attendance system.

Core tables:
- students / embeddings: enrolled face data. Each student belongs to a class.
- teachers / classes / subjects / class_subjects / teacher_assignments:
  the academic structure - who teaches which subject in which class, and
  which subjects exist in which class. Populated by scripts/seed_academic_data.py,
  not through the app.
- attendance: the single source of truth for who was marked present, scoped
  to a specific class + subject + date. Excel is GENERATED from this table
  by excel_writer.py; nothing writes to Excel directly, so the DB and the
  report can never drift apart.

Why SQLite: indexed lookups instead of loading everything into memory, safe
concurrent writes (WAL mode), and a straight upgrade path to Postgres later
if this ever goes multi-campus - same SQL, just swap the connection string.
"""

import sqlite3
import os
import hashlib
import hmac
from datetime import datetime

import numpy as np

from config import DB_PATH


def get_connection():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")  # allows concurrent reads while writing
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _table_columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_students_table(conn):
    """Adds class_id to a students table created before classes existed."""
    if _table_exists(conn, "students") and "class_id" not in _table_columns(conn, "students"):
        conn.execute("ALTER TABLE students ADD COLUMN class_id INTEGER REFERENCES classes(id)")


def _migrate_attendance_table(conn):
    """
    Attendance moved from UNIQUE(roll_no, date) to UNIQUE(roll_no, class_id,
    subject_id, date) - a student can now legitimately have more than one
    attendance row on the same date, one per subject. SQLite can't alter a
    UNIQUE constraint in place, so an old-shaped table is renamed, replaced,
    and its rows copied across (class_id/subject_id/teacher_id come in as
    NULL - harmless, since NULL is never treated as a duplicate in a UNIQUE
    index). Pre-existing rows are intentionally left unlinked to any
    class/subject rather than guessed at.
    """
    if not _table_exists(conn, "attendance"):
        conn.execute(
            """
            CREATE TABLE attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                roll_no TEXT NOT NULL,
                name TEXT NOT NULL,
                class_id INTEGER,
                subject_id INTEGER,
                teacher_id INTEGER,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                status TEXT NOT NULL,
                source TEXT NOT NULL,
                UNIQUE(roll_no, class_id, subject_id, date),
                FOREIGN KEY (class_id) REFERENCES classes(id),
                FOREIGN KEY (subject_id) REFERENCES subjects(id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(id)
            );
            """
        )
        return

    if "class_id" in _table_columns(conn, "attendance"):
        return  # already migrated

    conn.execute("ALTER TABLE attendance RENAME TO attendance_legacy;")
    conn.execute(
        """
        CREATE TABLE attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT NOT NULL,
            name TEXT NOT NULL,
            class_id INTEGER,
            subject_id INTEGER,
            teacher_id INTEGER,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT NOT NULL,
            source TEXT NOT NULL,
            UNIQUE(roll_no, class_id, subject_id, date),
            FOREIGN KEY (class_id) REFERENCES classes(id),
            FOREIGN KEY (subject_id) REFERENCES subjects(id),
            FOREIGN KEY (teacher_id) REFERENCES teachers(id)
        );
        """
    )
    conn.execute(
        """
        INSERT INTO attendance (roll_no, name, date, time, status, source)
        SELECT roll_no, name, date, time, status, source FROM attendance_legacy
        """
    )
    conn.execute("DROP TABLE attendance_legacy;")


def init_db():
    conn = get_connection()

    # Academic structure first - attendance/students reference these.
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS class_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL REFERENCES classes(id),
            subject_id INTEGER NOT NULL REFERENCES subjects(id),
            UNIQUE(class_id, subject_id)
        );

        CREATE TABLE IF NOT EXISTS teacher_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL REFERENCES teachers(id),
            class_id INTEGER NOT NULL REFERENCES classes(id),
            subject_id INTEGER NOT NULL REFERENCES subjects(id),
            UNIQUE(teacher_id, class_id, subject_id)
        );

        CREATE TABLE IF NOT EXISTS students (
            roll_no TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            class_id INTEGER REFERENCES classes(id)
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT NOT NULL,
            embedding BLOB NOT NULL,
            source_photo TEXT,
            enrolled_on TEXT NOT NULL,
            FOREIGN KEY (roll_no) REFERENCES students(roll_no) ON DELETE CASCADE
        );
        """
    )

    _migrate_students_table(conn)
    _migrate_attendance_table(conn)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------- Passwords

_HASH_ITERATIONS = 260_000


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _HASH_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password, stored_hash):
    salt_hex, digest_hex = stored_hash.split("$")
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _HASH_ITERATIONS)
    return hmac.compare_digest(actual, expected)


# ------------------------------------------------------------- Academic data

def add_teacher(username, password, name):
    """Insert a new teacher, or update name/password if the username already
    exists - makes the seed script safe to rerun after editing."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO teachers (username, password_hash, name) VALUES (?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, name = excluded.name
        """,
        (username, hash_password(password), name),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM teachers WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row[0]


def verify_teacher_login(username, password):
    conn = get_connection()
    row = conn.execute(
        "SELECT id, name, password_hash FROM teachers WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    teacher_id, name, password_hash = row
    if verify_password(password, password_hash):
        return {"id": teacher_id, "name": name, "username": username}
    return None


def add_class(name):
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO classes (name) VALUES (?)", (name,))
    conn.commit()
    row = conn.execute("SELECT id FROM classes WHERE name = ?", (name,)).fetchone()
    conn.close()
    return row[0]


def add_subject(name):
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO subjects (name) VALUES (?)", (name,))
    conn.commit()
    row = conn.execute("SELECT id FROM subjects WHERE name = ?", (name,)).fetchone()
    conn.close()
    return row[0]


def add_class_subject(class_id, subject_id):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO class_subjects (class_id, subject_id) VALUES (?, ?)",
        (class_id, subject_id),
    )
    conn.commit()
    conn.close()


def add_teacher_assignment(teacher_id, class_id, subject_id):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO teacher_assignments (teacher_id, class_id, subject_id) VALUES (?, ?, ?)",
        (teacher_id, class_id, subject_id),
    )
    conn.commit()
    conn.close()


def get_all_classes():
    conn = get_connection()
    rows = conn.execute("SELECT id, name FROM classes ORDER BY name").fetchall()
    conn.close()
    return rows


def get_class_id_by_name(name):
    conn = get_connection()
    row = conn.execute("SELECT id FROM classes WHERE name = ?", (name,)).fetchone()
    conn.close()
    return row[0] if row else None


def get_subject_id_by_name(name):
    conn = get_connection()
    row = conn.execute("SELECT id FROM subjects WHERE name = ?", (name,)).fetchone()
    conn.close()
    return row[0] if row else None


def get_teacher_id_by_username(username):
    conn = get_connection()
    row = conn.execute("SELECT id FROM teachers WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row[0] if row else None


def get_class_name(class_id):
    conn = get_connection()
    row = conn.execute("SELECT name FROM classes WHERE id = ?", (class_id,)).fetchone()
    conn.close()
    return row[0] if row else None


def get_subject_name(subject_id):
    conn = get_connection()
    row = conn.execute("SELECT name FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    conn.close()
    return row[0] if row else None


def get_classes_for_teacher(teacher_id):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT DISTINCT c.id, c.name
        FROM teacher_assignments ta
        JOIN classes c ON c.id = ta.class_id
        WHERE ta.teacher_id = ?
        ORDER BY c.name
        """,
        (teacher_id,),
    ).fetchall()
    conn.close()
    return rows


def get_subjects_for_teacher_and_class(teacher_id, class_id):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT DISTINCT sub.id, sub.name
        FROM teacher_assignments ta
        JOIN subjects sub ON sub.id = ta.subject_id
        WHERE ta.teacher_id = ? AND ta.class_id = ?
        ORDER BY sub.name
        """,
        (teacher_id, class_id),
    ).fetchall()
    conn.close()
    return rows


# ------------------------------------------------------------------ Students

def add_student(roll_no, name, class_id=None):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO students (roll_no, name, class_id) VALUES (?, ?, ?)",
        (roll_no, name, class_id),
    )
    conn.commit()
    conn.close()


def set_student_class(roll_no, class_id):
    conn = get_connection()
    conn.execute("UPDATE students SET class_id = ? WHERE roll_no = ?", (class_id, roll_no))
    conn.commit()
    conn.close()


def get_students_by_class(class_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT roll_no, name FROM students WHERE class_id = ? ORDER BY name",
        (class_id,),
    ).fetchall()
    conn.close()
    return rows


def add_embedding(roll_no, embedding, source_photo=None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO embeddings (roll_no, embedding, source_photo, enrolled_on) "
        "VALUES (?, ?, ?, ?)",
        (
            roll_no,
            embedding.astype(np.float64).tobytes(),
            source_photo,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_enrolled_photo_names(roll_no):
    """Photo filenames already embedded for this student, so enroll_student()
    can skip re-processing photos it has already saved."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT source_photo FROM embeddings WHERE roll_no = ?",
        (roll_no,),
    ).fetchall()
    conn.close()
    return {row[0] for row in rows}


def get_all_embeddings(class_id=None):
    """
    Returns: { roll_no: {"name": str, "embeddings": [np.ndarray, ...]} }
    Loaded once per recognition run, then matched in memory.

    class_id restricts this to one class's students, so a face belonging to
    a student in a different class is never even considered a candidate
    match during that class's attendance session.
    """
    conn = get_connection()
    if class_id is None:
        rows = conn.execute(
            """
            SELECT s.roll_no, s.name, e.embedding
            FROM embeddings e
            JOIN students s ON s.roll_no = e.roll_no
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT s.roll_no, s.name, e.embedding
            FROM embeddings e
            JOIN students s ON s.roll_no = e.roll_no
            WHERE s.class_id = ?
            """,
            (class_id,),
        ).fetchall()
    conn.close()

    enrolled = {}
    for roll_no, name, blob in rows:
        vector = np.frombuffer(blob, dtype=np.float64)
        enrolled.setdefault(roll_no, {"name": name, "embeddings": []})
        enrolled[roll_no]["embeddings"].append(vector)
    return enrolled


# --------------------------------------------------------------- Attendance

def mark_attendance(roll_no, name, class_id, subject_id, teacher_id, date, time, source, status="Present"):
    """
    Returns True if a new row was inserted, False if this student was
    already marked for this class+subject+date. De-duplication is enforced
    by the UNIQUE(roll_no, class_id, subject_id, date) constraint, not
    application logic.
    """
    conn = get_connection()
    cursor = conn.execute(
        "INSERT OR IGNORE INTO attendance (roll_no, name, class_id, subject_id, teacher_id, date, time, status, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (roll_no, name, class_id, subject_id, teacher_id, date, time, status, source),
    )
    conn.commit()
    inserted = cursor.rowcount > 0
    conn.close()
    return inserted


def get_attendance_for_session(class_id, subject_id, date):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT roll_no, name, date, time, status, source
        FROM attendance
        WHERE class_id = ? AND subject_id = ? AND date = ?
        ORDER BY name
        """,
        (class_id, subject_id, date),
    ).fetchall()
    conn.close()
    return rows


def delete_attendance(roll_no, class_id, subject_id, date):
    """Removes one student's attendance row for a class+subject+date. Returns True if a row was deleted."""
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM attendance WHERE roll_no = ? AND class_id = ? AND subject_id = ? AND date = ?",
        (roll_no, class_id, subject_id, date),
    )
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted
