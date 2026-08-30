"""
SQLite storage layer for the attendance system.

Two things live here:
- students / embeddings tables: enrolled face data
- attendance table: daily attendance records - this is the single source of
  truth. Excel is GENERATED from this table by excel_writer.py; nothing
  writes to Excel directly, so the DB and the report can never drift apart.

Why SQLite: indexed lookups by roll_no instead of loading everything into
memory, safe concurrent writes (WAL mode), and a straight upgrade path to
Postgres later if this ever goes multi-campus - same SQL, just swap the
connection string.
"""

import sqlite3
import os
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


def init_db():
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS students (
            roll_no TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT NOT NULL,
            embedding BLOB NOT NULL,
            source_photo TEXT,
            enrolled_on TEXT NOT NULL,
            FOREIGN KEY (roll_no) REFERENCES students(roll_no) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT NOT NULL,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT NOT NULL,
            source TEXT NOT NULL,
            UNIQUE(roll_no, date)
        );
        """
    )
    conn.commit()
    conn.close()


def add_student(roll_no, name):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO students (roll_no, name) VALUES (?, ?)",
        (roll_no, name),
    )
    conn.commit()
    conn.close()


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


def get_all_embeddings():
    """
    Returns: { roll_no: {"name": str, "embeddings": [np.ndarray, ...]} }
    Loaded once per recognition run, then matched in memory.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT s.roll_no, s.name, e.embedding
        FROM embeddings e
        JOIN students s ON s.roll_no = e.roll_no
        """
    ).fetchall()
    conn.close()

    enrolled = {}
    for roll_no, name, blob in rows:
        vector = np.frombuffer(blob, dtype=np.float64)
        enrolled.setdefault(roll_no, {"name": name, "embeddings": []})
        enrolled[roll_no]["embeddings"].append(vector)
    return enrolled


def mark_attendance(roll_no, name, date, time, source, status="Present"):
    """
    Returns True if a new row was inserted, False if this student was
    already marked for this date. De-duplication is enforced by the
    UNIQUE(roll_no, date) constraint, not application logic.
    """
    conn = get_connection()
    cursor = conn.execute(
        "INSERT OR IGNORE INTO attendance (roll_no, name, date, time, status, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (roll_no, name, date, time, status, source),
    )
    conn.commit()
    inserted = cursor.rowcount > 0
    conn.close()
    return inserted


def get_attendance_for_date(date):
    conn = get_connection()
    rows = conn.execute(
        "SELECT roll_no, name, date, time, status, source "
        "FROM attendance WHERE date = ? ORDER BY name",
        (date,),
    ).fetchall()
    conn.close()
    return rows


def get_all_students():
    """Full roster, regardless of whether they've ever been marked present."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT roll_no, name FROM students ORDER BY name"
    ).fetchall()
    conn.close()
    return rows


def delete_attendance(roll_no, date):
    """Removes one student's attendance row for a date. Returns True if a row was deleted."""
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM attendance WHERE roll_no = ? AND date = ?",
        (roll_no, date),
    )
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted
