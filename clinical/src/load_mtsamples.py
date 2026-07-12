"""Load, clean, section, and store MTSamples notes into SQLite.

Run:
    python -m clinical.src.load_mtsamples            # download if needed, then load
    python -m clinical.src.load_mtsamples --force    # re-download raw CSV first

Produces:
    clinical/data/clinical.db  (table: clinical_notes)

Cleaning performed:
  * drop rows with empty transcriptions
  * strip + collapse whitespace
  * normalize the medical_specialty label (MTSamples has leading spaces)
  * drop exact-duplicate transcriptions
  * split each note into sections (see sectioner.py)
  * compute char / word / section counts
"""
from __future__ import annotations

import json
import re
import sys
from typing import Dict, List

import pandas as pd

from . import config, db
from .download_data import acquire
from .sectioner import split_sections

_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def _clean_text(text: str) -> str:
    """Normalize whitespace without destroying line structure needed for sections."""
    if not isinstance(text, str):
        return ""
    text = text.replace("\u00a0", " ")            # non-breaking spaces
    text = _WS_RE.sub(" ", text)                    # collapse runs of spaces/tabs
    text = _MULTI_NL_RE.sub("\n\n", text)          # cap consecutive newlines
    return text.strip()


def _clean_specialty(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return "Unknown"
    return value.strip()


def load_dataframe() -> pd.DataFrame:
    """Read + clean the raw MTSamples CSV into a tidy DataFrame."""
    csv_path = acquire()
    print(f"[load] Reading {csv_path} ...")
    df = pd.read_csv(csv_path)

    # The Kaggle file has an unnamed index column; drop any such columns.
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]
    df.columns = [c.strip().lower() for c in df.columns]

    missing = [c for c in config.EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"MTSamples CSV missing expected columns: {missing}. Found: {list(df.columns)}"
        )

    n_raw = len(df)

    # Clean text fields.
    df["transcription"] = df["transcription"].map(_clean_text)
    df["medical_specialty"] = df["medical_specialty"].map(_clean_specialty)
    for col in ("description", "sample_name", "keywords"):
        df[col] = df[col].fillna("").map(lambda x: x.strip() if isinstance(x, str) else "")

    # Drop empty + duplicate transcriptions.
    df = df[df["transcription"].str.len() > 0].copy()
    n_empty_dropped = n_raw - len(df)
    df = df.drop_duplicates(subset=["transcription"], keep="first").copy()
    n_dupe_dropped = (n_raw - n_empty_dropped) - len(df)

    # Derived fields.
    df["char_count"] = df["transcription"].str.len()
    df["word_count"] = df["transcription"].str.split().map(len)

    sections_list: List[Dict[str, str]] = []
    section_counts: List[int] = []
    for text in df["transcription"]:
        secs = split_sections(text)
        sections_list.append(secs)
        # "UNSECTIONED" means no real headers were found -> 0 detected sections.
        real = {k: v for k, v in secs.items() if k != "UNSECTIONED"}
        section_counts.append(len(real))
    df["sections"] = sections_list
    df["section_count"] = section_counts
    df["sections_json"] = [json.dumps(s, ensure_ascii=False) for s in sections_list]

    print(
        f"[load] rows: {n_raw} raw -> {len(df)} kept "
        f"(dropped {n_empty_dropped} empty, {n_dupe_dropped} duplicates)"
    )
    return df


def store_dataframe(df: pd.DataFrame) -> int:
    conn = db.connect()
    try:
        db.init_db(conn)
        db.reset_notes(conn)
        rows = [
            {
                "sample_name": r.sample_name,
                "description": r.description,
                "medical_specialty": r.medical_specialty,
                "keywords": r.keywords,
                "transcription": r.transcription,
                "char_count": int(r.char_count),
                "word_count": int(r.word_count),
                "section_count": int(r.section_count),
                "sections_json": r.sections_json,
            }
            for r in df.itertuples(index=False)
        ]
        n = db.insert_notes(conn, rows)
        total = db.count_notes(conn)
        print(f"[load] Inserted {n} notes -> {config.DB_PATH} (table has {total} rows).")
        return n
    finally:
        conn.close()


def print_quick_summary(df: pd.DataFrame) -> None:
    print("\n=== Quick summary ===")
    print(f"Notes:            {len(df)}")
    print(f"Specialties:      {df['medical_specialty'].nunique()}")
    print(f"Median words:     {int(df['word_count'].median())}")
    print(f"Median sections:  {int(df['section_count'].median())}")
    print("\nTop 10 specialties:")
    print(df["medical_specialty"].value_counts().head(10).to_string())


def main() -> None:
    config.ensure_dirs()
    if "--force" in sys.argv:
        acquire(force=True)
    df = load_dataframe()
    store_dataframe(df)
    print_quick_summary(df)
    print("\n[load] Done. Next: run EDA ->  python -m clinical.src.eda")


if __name__ == "__main__":
    main()
