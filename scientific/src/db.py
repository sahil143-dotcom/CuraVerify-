"""SQLite schema for the scientific arm (papers / summaries / verdicts)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id     TEXT UNIQUE NOT NULL,
    source          TEXT NOT NULL,
    split           TEXT NOT NULL,
    title           TEXT NOT NULL,
    year            TEXT,
    keywords_json   TEXT,
    sections_json   TEXT,
    article         TEXT NOT NULL,
    char_count      INTEGER NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS summaries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id            INTEGER NOT NULL,
    summary_text        TEXT NOT NULL,
    is_real             INTEGER NOT NULL,
    source              TEXT,
    perturbation_type   TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paper_id) REFERENCES papers(id)
);

CREATE TABLE IF NOT EXISTS verification_results (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    summary_id              INTEGER NOT NULL,
    sentence_idx            INTEGER NOT NULL,
    sentence_text           TEXT NOT NULL,
    grade                   TEXT NOT NULL,
    hallucination_type      TEXT,
    citations_json          TEXT,
    reasoning               TEXT,
    confidence              REAL,
    claims_json             TEXT,
    evidence_package_json   TEXT,
    method                  TEXT DEFAULT 'graphrag',
    verified_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (summary_id) REFERENCES summaries(id)
);

CREATE TABLE IF NOT EXISTS document_verdicts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    summary_id          INTEGER NOT NULL,
    total_sentences     INTEGER NOT NULL,
    count_e1            INTEGER NOT NULL,
    count_e2            INTEGER NOT NULL,
    count_e3            INTEGER NOT NULL,
    count_e4            INTEGER NOT NULL,
    hallucination_rate  REAL,
    contradiction_rate  REAL,
    overall_verdict     TEXT,
    method              TEXT DEFAULT 'graphrag',
    FOREIGN KEY (summary_id) REFERENCES summaries(id)
);

CREATE INDEX IF NOT EXISTS idx_papers_source_split ON papers(source, split);
CREATE INDEX IF NOT EXISTS idx_summaries_paper ON summaries(paper_id);
CREATE INDEX IF NOT EXISTS idx_vr_summary ON verification_results(summary_id);
"""


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def reset_all(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM verification_results;
        DELETE FROM document_verdicts;
        DELETE FROM summaries;
        DELETE FROM papers;
        """
    )
    conn.commit()


def upsert_paper(conn: sqlite3.Connection, row: Mapping) -> int:
    cur = conn.execute(
        """
        INSERT INTO papers
            (external_id, source, split, title, year, keywords_json,
             sections_json, article, char_count)
        VALUES
            (:external_id, :source, :split, :title, :year, :keywords_json,
             :sections_json, :article, :char_count)
        ON CONFLICT(external_id) DO UPDATE SET
            title=excluded.title,
            article=excluded.article,
            sections_json=excluded.sections_json
        """,
        dict(row),
    )
    conn.commit()
    if cur.lastrowid:
        return int(cur.lastrowid)
    got = conn.execute(
        "SELECT id FROM papers WHERE external_id = ?", (row["external_id"],)
    ).fetchone()
    return int(got["id"])


def insert_summary(conn: sqlite3.Connection, row: Mapping) -> int:
    cur = conn.execute(
        """
        INSERT INTO summaries
            (paper_id, summary_text, is_real, source, perturbation_type)
        VALUES
            (:paper_id, :summary_text, :is_real, :source, :perturbation_type)
        """,
        dict(row),
    )
    conn.commit()
    return int(cur.lastrowid)


def insert_verification_rows(conn: sqlite3.Connection, rows: Iterable[Mapping]) -> int:
    rows = list(rows)
    conn.executemany(
        """
        INSERT INTO verification_results
            (summary_id, sentence_idx, sentence_text, grade, hallucination_type,
             citations_json, reasoning, confidence, claims_json,
             evidence_package_json, method)
        VALUES
            (:summary_id, :sentence_idx, :sentence_text, :grade, :hallucination_type,
             :citations_json, :reasoning, :confidence, :claims_json,
             :evidence_package_json, :method)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def insert_document_verdict(conn: sqlite3.Connection, row: Mapping) -> int:
    cur = conn.execute(
        """
        INSERT INTO document_verdicts
            (summary_id, total_sentences, count_e1, count_e2, count_e3, count_e4,
             hallucination_rate, contradiction_rate, overall_verdict, method)
        VALUES
            (:summary_id, :total_sentences, :count_e1, :count_e2, :count_e3, :count_e4,
             :hallucination_rate, :contradiction_rate, :overall_verdict, :method)
        """,
        dict(row),
    )
    conn.commit()
    return int(cur.lastrowid)


def count_papers(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0])


def count_summaries(conn: sqlite3.Connection, real_only: bool | None = None) -> int:
    if real_only is None:
        return int(conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0])
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM summaries WHERE is_real = ?",
            (1 if real_only else 0,),
        ).fetchone()[0]
    )
