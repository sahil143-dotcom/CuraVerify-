"""Download BioLaySumm 2025 Task-1 datasets essential for CuraVerify.

Space-aware strategy (avoids filling the disk with the full 540MB PLOS train set):
  - eLife: download ALL splits (small ~136MB)
  - PLOS: download validation + test fully, plus a TRAIN SAMPLE (default 800)

Skipped (not needed for CuraVerify core):
  - LaymanRRG radiology / multimodal tracks

Run from repo root:
    py -m scientific.src.download_biolaysumm
    py -m scientific.src.download_biolaysumm --plos-train 200
    py -m scientific.src.download_biolaysumm --full-plos   # only if you have ~2GB free
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "scientific" / "data" / "biolaysumm"


def _write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in rows:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _row_to_rec(row, source: str, split: str) -> dict:
    return {
        "title": row.get("title", ""),
        "article": row.get("article", ""),
        "summary": row.get("summary", ""),
        "section_headings": list(row.get("section_headings") or []),
        "keywords": list(row.get("keywords") or []),
        "year": row.get("year", ""),
        "source": source,
        "split": split,
    }


def _stats(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "article_chars_median": 0, "summary_chars_median": 0}
    arts = sorted(len(r["article"]) for r in rows)
    sums = sorted(len(r["summary"]) for r in rows)
    return {
        "n": n,
        "article_chars_median": arts[n // 2],
        "summary_chars_median": sums[n // 2],
        "article_chars_mean": int(sum(arts) / n),
        "summary_chars_mean": int(sum(sums) / n),
    }


def _export_split(ds_split, source: str, split: str, dest: Path, limit: int | None = None) -> dict:
    rows = []
    for i, row in enumerate(ds_split):
        if limit is not None and i >= limit:
            break
        rows.append(_row_to_rec(row, source, split if limit is None else f"{split}_sample"))
    out = dest / f"{'train_sample' if limit is not None else split}.jsonl"
    _write_jsonl(rows, out)
    st = _stats(rows)
    st["jsonl"] = str(out)
    print(f"  [{source}/{out.name}] {st['n']} rows")
    return st


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plos-train", type=int, default=800, help="Train sample size for PLOS")
    parser.add_argument("--full-plos", action="store_true", help="Download full PLOS train (needs disk)")
    parser.add_argument("--elife-only", action="store_true", help="Skip PLOS entirely")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from datasets import load_dataset
    except ImportError:
        print("[error] Missing dependency. Install with:")
        print("  py -m pip install datasets huggingface_hub pyarrow")
        sys.exit(1)

    report: dict = {
        "output_dir": str(OUT_DIR),
        "strategy": "full eLife + PLOS val/test + PLOS train sample"
        if not args.full_plos
        else "full eLife + full PLOS",
        "datasets": {},
    }

    # --- eLife (essential, smaller) ---
    print("=" * 72)
    print("[download] BioLaySumm/BioLaySumm2025-eLife")
    elife = load_dataset("BioLaySumm/BioLaySumm2025-eLife")
    elife_dir = OUT_DIR / "eLife"
    elife_dir.mkdir(parents=True, exist_ok=True)
    elife_stats = {}
    for split in elife:
        elife_stats[split] = _export_split(elife[split], "eLife", split, elife_dir)
    report["datasets"]["eLife"] = {
        "hf_id": "BioLaySumm/BioLaySumm2025-eLife",
        "disk": str(elife_dir),
        "splits": elife_stats,
    }

    # --- PLOS (essential; sample train to save disk) ---
    if not args.elife_only:
        print("=" * 72)
        print("[download] BioLaySumm/BioLaySumm2025-PLOS")
        # Load splits separately so we can avoid materializing full train unless asked.
        plos_dir = OUT_DIR / "PLOS"
        plos_dir.mkdir(parents=True, exist_ok=True)
        plos_stats = {}

        for split in ("validation", "test"):
            print(f"  loading PLOS/{split} ...")
            part = load_dataset("BioLaySumm/BioLaySumm2025-PLOS", split=split)
            plos_stats[split] = _export_split(part, "PLOS", split, plos_dir)

        if args.full_plos:
            print("  loading full PLOS/train (large) ...")
            train = load_dataset("BioLaySumm/BioLaySumm2025-PLOS", split="train")
            plos_stats["train"] = _export_split(train, "PLOS", "train", plos_dir)
        else:
            # Stream train so we do NOT download the full ~540MB split.
            print(f"  streaming PLOS/train sample (n={args.plos_train}) ...")
            train_stream = load_dataset(
                "BioLaySumm/BioLaySumm2025-PLOS", split="train", streaming=True
            )
            rows = []
            for i, row in enumerate(train_stream):
                if i >= args.plos_train:
                    break
                rows.append(_row_to_rec(row, "PLOS", "train_sample"))
            out = plos_dir / "train_sample.jsonl"
            _write_jsonl(rows, out)
            st = _stats(rows)
            st["jsonl"] = str(out)
            plos_stats["train_sample"] = st
            print(f"  [PLOS/{out.name}] {st['n']} rows (streamed; use --full-plos for all)")

        report["datasets"]["PLOS"] = {
            "hf_id": "BioLaySumm/BioLaySumm2025-PLOS",
            "disk": str(plos_dir),
            "splits": plos_stats,
        }

    # Combined preview sample for demos (5 from each available source)
    preview = []
    for name, info in report["datasets"].items():
        # Prefer validation jsonl
        splits = info["splits"]
        key = "validation" if "validation" in splits else next(iter(splits))
        path = Path(splits[key]["jsonl"])
        with path.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 3:
                    break
                preview.append(json.loads(line))
    preview_path = OUT_DIR / "preview_samples.json"
    preview_path.write_text(json.dumps(preview, indent=2, ensure_ascii=False), encoding="utf-8")

    report_path = OUT_DIR / "download_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = [
        "# BioLaySumm → CuraVerify Download Summary",
        "",
        "## What the website offers",
        "",
        "| Track | Datasets | Essential for CuraVerify? |",
        "|---|---|---|",
        "| Task 1 Lay summarization | PLOS, eLife (article ↔ lay summary) | **YES** |",
        "| Task 2 Radiology lay terms | PadChest, BIMCV, Open-i, MIMIC-CXR | No (images / RRG) |",
        "",
        f"**Downloaded strategy:** {report['strategy']}",
        "",
        f"Output: `{OUT_DIR}`",
        "",
    ]
    for name, info in report["datasets"].items():
        md.append(f"## {name}")
        md.append("")
        md.append("| Split | Rows | Median article chars | Median summary chars |")
        md.append("|---|---:|---:|---:|")
        for split, st in info["splits"].items():
            md.append(
                f"| {split} | {st['n']} | {st['article_chars_median']} | {st['summary_chars_median']} |"
            )
        md.append("")

    md.extend(
        [
            "## Schema (both datasets)",
            "",
            "| Field | CuraVerify role |",
            "|---|---|",
            "| `article` | Source document (ground truth) |",
            "| `summary` | Lay summary to verify |",
            "| `section_headings` | Structure for evidence retrieval |",
            "| `title`, `keywords`, `year` | Metadata |",
            "",
            "## Next step for CuraVerify",
            "",
            "1. Split each `summary` into atomic claims",
            "2. Retrieve evidence snippets from `article`",
            "3. Grade E1–E4 (support / weak / none / contradict)",
            "4. Optionally inject controlled hallucinations into summaries for eval",
            "",
            f"Preview samples: `{preview_path}`",
            "",
        ]
    )
    md_path = OUT_DIR / "DOWNLOAD_SUMMARY.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    print("=" * 72)
    print(f"[done] {report_path}")
    print(f"[done] {md_path}")
    print(f"[done] {preview_path}")
    total = sum(st["n"] for info in report["datasets"].values() for st in info["splits"].values())
    print(f"[done] Total exported rows: {total}")


if __name__ == "__main__":
    main()
