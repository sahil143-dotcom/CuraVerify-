"""Acquire the MTSamples dataset into data/raw/mtsamples.csv.

Strategy (first success wins):
  1. If the file already exists and looks valid -> reuse it.
  2. Try `kagglehub` (official Kaggle dataset, most reliable + up to date).
  3. Try each public raw mirror in config.MTSAMPLES_MIRRORS.
  4. If everything fails, print clear manual-download instructions and exit(1).

The downloaded file is validated (parses as CSV, has the expected columns,
has a reasonable row count) before being accepted.
"""
from __future__ import annotations

import csv
import io
import shutil
import sys
import urllib.request
from pathlib import Path

from . import config

_MIN_ROWS = 1000          # MTSamples has ~5k rows; guard against truncated mirrors
_MIN_BYTES = 500_000      # ~ full file is several MB; reject tiny error pages


def _looks_like_valid_csv(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < _MIN_BYTES:
        return False
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None:
                return False
            header_lower = {h.strip().lower() for h in header}
            required = {"transcription", "medical_specialty"}
            if not required.issubset(header_lower):
                return False
            rows = sum(1 for _ in reader)
            return rows >= _MIN_ROWS
    except Exception:
        return False


def _try_kagglehub() -> bool:
    try:
        import kagglehub  # type: ignore
    except ImportError:
        print("[download] kagglehub not installed; skipping Kaggle route.")
        return False
    try:
        print(f"[download] Trying Kaggle dataset '{config.KAGGLE_DATASET}' via kagglehub ...")
        cache_dir = Path(kagglehub.dataset_download(config.KAGGLE_DATASET))
        # find mtsamples.csv within the downloaded folder
        candidates = list(cache_dir.rglob("*.csv"))
        for c in candidates:
            if "mtsample" in c.name.lower() or _looks_like_valid_csv(c):
                shutil.copyfile(c, config.MTSAMPLES_CSV)
                print(f"[download] Copied {c.name} from Kaggle cache.")
                return _looks_like_valid_csv(config.MTSAMPLES_CSV)
        print("[download] kagglehub succeeded but no valid CSV found in the download.")
        return False
    except Exception as e:  # noqa: BLE001 - report and fall through to mirrors
        print(f"[download] kagglehub route failed: {e}")
        return False


def _try_mirror(url: str) -> bool:
    try:
        print(f"[download] Trying mirror: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "curaverify-clinical/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - trusted mirrors
            data = resp.read()
        if len(data) < _MIN_BYTES:
            print(f"[download]   rejected: only {len(data)} bytes.")
            return False
        config.MTSAMPLES_CSV.write_bytes(data)
        if _looks_like_valid_csv(config.MTSAMPLES_CSV):
            print(f"[download]   OK ({len(data):,} bytes).")
            return True
        print("[download]   rejected: downloaded file failed validation.")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"[download]   failed: {e}")
        return False


def _manual_instructions() -> None:
    print(
        "\n"
        "========================================================================\n"
        " Could not fetch MTSamples automatically.\n"
        " Download it manually (one of these), then place it at:\n"
        f"   {config.MTSAMPLES_CSV}\n"
        "\n"
        " Option A (Kaggle, recommended):\n"
        "   https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions\n"
        "   -> download 'mtsamples.csv'\n"
        "\n"
        " Option B (Kaggle CLI):\n"
        "   pip install kaggle\n"
        "   kaggle datasets download -d tboyle10/medicaltranscriptions -f mtsamples.csv\n"
        "\n"
        " Then re-run:  python -m clinical.src.load_mtsamples\n"
        "========================================================================\n"
    )


def acquire(force: bool = False) -> Path:
    """Ensure data/raw/mtsamples.csv exists and is valid. Returns its path."""
    config.ensure_dirs()

    if not force and _looks_like_valid_csv(config.MTSAMPLES_CSV):
        print(f"[download] Reusing existing valid file: {config.MTSAMPLES_CSV}")
        return config.MTSAMPLES_CSV

    if _try_kagglehub():
        return config.MTSAMPLES_CSV

    for url in config.MTSAMPLES_MIRRORS:
        if _try_mirror(url):
            return config.MTSAMPLES_CSV

    _manual_instructions()
    sys.exit(1)


if __name__ == "__main__":
    force = "--force" in sys.argv
    path = acquire(force=force)
    print(f"[download] Ready: {path}")
