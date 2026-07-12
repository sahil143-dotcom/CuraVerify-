"""Day 1 orchestrator: acquire -> load -> EDA, in one command.

From the repo root (D:\\CuraVerify):
    python -m clinical.run_day1
    python -m clinical.run_day1 --force   # force re-download of raw CSV
"""
from __future__ import annotations

import sys


def main() -> None:
    force = "--force" in sys.argv
    print("=" * 72)
    print(" CuraVerify Clinical — Day 1: data acquisition + EDA")
    print("=" * 72)

    # Imports are deferred so a partial environment still gets as far as possible
    # and produces an actionable error instead of failing at module load.
    from clinical.src import load_mtsamples
    from clinical.src.download_data import acquire

    print("\n[1/3] Acquiring MTSamples ...")
    acquire(force=force)

    print("\n[2/3] Loading + cleaning into SQLite ...")
    df = load_mtsamples.load_dataframe()
    load_mtsamples.store_dataframe(df)
    load_mtsamples.print_quick_summary(df)

    print("\n[3/3] Running EDA ...")
    try:
        from clinical.src import eda
        eda.main()
    except ModuleNotFoundError as e:
        print(f"[warn] Skipping EDA figures: missing dependency ({e.name}).")
        print("       Install it with:  <your-python> -m pip install matplotlib")
        print("       The database is built; you can re-run EDA later:")
        print("       <your-python> -m clinical.src.eda")

    print("\nDay 1 complete. Deliverables:")
    print("  - clinical/data/clinical.db      (clinical_notes table)")
    print("  - clinical/results/*.png         (EDA figures)")
    print("  - clinical/results/eda_report.md (EDA summary)")


if __name__ == "__main__":
    main()
