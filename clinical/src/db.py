"""SQLite schema + helpers for the clinical arm.

The `clinical_notes` table mirrors the shape of CuraVerify's `papers` table
(see DATA_SCHEMA.md) but for clinical transcriptions instead of scientific
papers, so the downstream KG / verifier layers can be ported cleanly.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS clinical_notes (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_name        TEXT,                       -- e.g. "Cardiology Consult - 1"
    description        TEXT,                       -- one-line description
    medical_specialty  TEXT NOT NULL,              -- normalized specialty label
    keywords           TEXT,                       -- comma-separated keywords
    transcription      TEXT NOT NULL,              -- cleaned full note text
    char_count         INTEGER NOT NULL,
    word_count         INTEGER NOT NULL,
    section_count      INTEGER NOT NULL,
    sections_json      TEXT NOT NULL,              -- JSON {header: body}
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notes_specialty
    ON clinical_notes (medical_specialty);
"""


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def reset_notes(conn: sqlite3.Connection) -> None:
    """Drop existing rows so re-runs are idempotent."""
    conn.execute("DELETE FROM clinical_notes;")
    conn.commit()


def insert_notes(conn: sqlite3.Connection, rows: Iterable[Mapping]) -> int:
    sql = """
        INSERT INTO clinical_notes
            (sample_name, description, medical_specialty, keywords,
             transcription, char_count, word_count, section_count, sections_json)
        VALUES
            (:sample_name, :description, :medical_specialty, :keywords,
             :transcription, :char_count, :word_count, :section_count, :sections_json)
    """
    rows = list(rows)
    conn.executemany(sql, rows)
    conn.commit()
    return len(rows)


def count_notes(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM clinical_notes;").fetchone()[0]
