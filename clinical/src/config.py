"""Central paths and constants for the clinical arm.

Everything is anchored to the `clinical/` directory so the pipeline runs
the same way regardless of the current working directory.
"""
from __future__ import annotations

from pathlib import Path

# clinical/src/config.py -> clinical/
CLINICAL_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = CLINICAL_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
RESULTS_DIR = CLINICAL_ROOT / "results"
NOTEBOOK_DIR = CLINICAL_ROOT / "notebooks"

# Raw dataset file (MTSamples)
MTSAMPLES_CSV = RAW_DIR / "mtsamples.csv"

# SQLite database that holds the cleaned notes
DB_PATH = DATA_DIR / "clinical.db"

# Kaggle dataset slug (used if kagglehub is available + configured)
KAGGLE_DATASET = "tboyle10/medicaltranscriptions"

# Public raw mirrors of mtsamples.csv, tried in order if kagglehub is unavailable.
# The loader validates each download before accepting it.
MTSAMPLES_MIRRORS = [
    "https://raw.githubusercontent.com/socd06/medical-nlp/master/data/mtsamples.csv",
    "https://raw.githubusercontent.com/mchmarny/tf-serving/master/data/mtsamples.csv",
    "https://raw.githubusercontent.com/ruslanmv/Medical-Chatbot/master/data/mtsamples.csv",
]

# Columns we expect in the raw MTSamples CSV.
EXPECTED_COLUMNS = [
    "description",
    "medical_specialty",
    "sample_name",
    "transcription",
    "keywords",
]


def ensure_dirs() -> None:
    """Create all output directories if they do not exist."""
    for d in (DATA_DIR, RAW_DIR, PROCESSED_DIR, RESULTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
