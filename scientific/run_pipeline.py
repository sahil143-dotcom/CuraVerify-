"""One-command CuraVerify scientific pipeline (CuraView 6 stages on BioLaySumm).

    py -m scientific.run_pipeline
    py -m scientific.run_pipeline --kg-limit 100 --hallucinate 40 --eval 40
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root on path when run as script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="CuraVerify BioLaySumm end-to-end pipeline")
    parser.add_argument("--kg-limit", type=int, default=200)
    parser.add_argument("--hallucinate", type=int, default=50)
    parser.add_argument("--eval", type=int, default=50)
    parser.add_argument("--skip-load", action="store_true")
    parser.add_argument("--skip-kg", action="store_true")
    parser.add_argument("--skip-hallucinate", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    args = parser.parse_args()

    from scientific.src import config
    from scientific.src.build_kg import build_for_papers
    from scientific.src.evaluate import compute_metrics, run_verification_batch, write_results
    from scientific.src.hallucinate import generate_hallucinated
    from scientific.src.load_biolaysumm import load

    config.ensure_dirs()
    print("=" * 72)
    print(" CuraVerify — BioLaySumm 6-stage pipeline")
    print("=" * 72)

    if not args.skip_load:
        print("\n[1/4] Stage 1 — Load BioLaySumm into SQLite ...")
        stats = load(reset=True)
        print(json.dumps(stats, indent=2))
    else:
        print("\n[1/4] Stage 1 — skipped")

    if not args.skip_kg:
        print(f"\n[2/4] Stages 2–3 — Build KGs (limit={args.kg_limit}) ...")
        print(json.dumps(build_for_papers(limit=args.kg_limit), indent=2))
    else:
        print("\n[2/4] KG build — skipped")

    if not args.skip_hallucinate:
        print(f"\n[3/4] Data curation — Hallucinate n={args.hallucinate} ...")
        print(json.dumps(generate_hallucinated(n=args.hallucinate), indent=2))
    else:
        print("\n[3/4] Hallucinate — skipped")

    if not args.skip_eval:
        print(f"\n[4/4] Stages 4–6 — Verify + evaluate (n={args.eval}) ...")
        print(json.dumps(run_verification_batch(limit=args.eval), indent=2))
        metrics = compute_metrics()
        path = write_results(metrics)
        print(json.dumps(metrics, indent=2))
        print(f"\nResults: {path}")
    else:
        print("\n[4/4] Eval — skipped")

    print("\nDone. Demo:")
    print("  streamlit run scientific/app.py")


if __name__ == "__main__":
    main()
