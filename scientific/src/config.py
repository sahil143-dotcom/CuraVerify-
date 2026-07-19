"""Paths and constants for the scientific (BioLaySumm) arm."""
from __future__ import annotations

from pathlib import Path

SCIENTIFIC_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SCIENTIFIC_ROOT.parent

DATA_DIR = SCIENTIFIC_ROOT / "data"
BIOLAYSUMM_DIR = DATA_DIR / "biolaysumm"
KG_DIR = DATA_DIR / "knowledge_graphs"
RESULTS_DIR = SCIENTIFIC_ROOT / "results"
DB_PATH = DATA_DIR / "scientific.db"

# Default pipeline sizes (plan profile)
DEFAULT_KG_LIMIT = 200
DEFAULT_HALLUCINATE_N = 50
DEFAULT_EVAL_N = 50

HALLUCINATION_TYPES = (
    "wrong_method",
    "wrong_value",
    "wrong_attribution",
    "missing_context",
    "invented_fact",
)

EVIDENCE_GRADES = ("E1", "E2", "E3", "E4")


def ensure_dirs() -> None:
    for d in (DATA_DIR, BIOLAYSUMM_DIR, KG_DIR, RESULTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
