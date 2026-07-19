"""Load BioLaySumm JSONL (train/val with gold summaries) into SQLite."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import config, db


def _external_id(source: str, split: str, title: str, article: str) -> str:
    h = hashlib.sha1(f"{source}|{split}|{title}|{article[:500]}".encode("utf-8")).hexdigest()[:16]
    return f"{source}_{split}_{h}"


def _iter_jsonl(path: Path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _usable_files() -> list[Path]:
    """Train/val (+ train_sample) only — official test summaries are blank."""
    files = []
    for source_dir in (config.BIOLAYSUMM_DIR / "eLife", config.BIOLAYSUMM_DIR / "PLOS"):
        if not source_dir.exists():
            continue
        for name in ("train.jsonl", "train_sample.jsonl", "validation.jsonl"):
            p = source_dir / name
            if p.exists():
                files.append(p)
    return files


def load(reset: bool = True) -> dict:
    config.ensure_dirs()
    files = _usable_files()
    if not files:
        raise SystemExit(
            "No BioLaySumm JSONL found. Run: py -m scientific.src.download_biolaysumm"
        )

    conn = db.connect()
    try:
        db.init_db(conn)
        if reset:
            db.reset_all(conn)

        n_papers = 0
        n_summaries = 0
        skipped_empty = 0

        for path in files:
            for rec in _iter_jsonl(path):
                summary = (rec.get("summary") or "").strip()
                article = (rec.get("article") or "").strip()
                if not article or not summary:
                    skipped_empty += 1
                    continue

                source = rec.get("source") or path.parent.name
                split = rec.get("split") or path.stem
                title = (rec.get("title") or "Untitled").strip()
                headings = rec.get("section_headings") or []
                keywords = rec.get("keywords") or []

                # Approximate section map from headings (article is flat text).
                sections = {"full": article}
                if headings:
                    sections["headings"] = " | ".join(str(h) for h in headings)

                ext_id = _external_id(source, split, title, article)
                paper_id = db.upsert_paper(
                    conn,
                    {
                        "external_id": ext_id,
                        "source": source,
                        "split": split,
                        "title": title,
                        "year": str(rec.get("year") or ""),
                        "keywords_json": json.dumps(keywords, ensure_ascii=False),
                        "sections_json": json.dumps(sections, ensure_ascii=False),
                        "article": article,
                        "char_count": len(article),
                    },
                )
                n_papers += 1

                db.insert_summary(
                    conn,
                    {
                        "paper_id": paper_id,
                        "summary_text": summary,
                        "is_real": 1,
                        "source": "biolaysumm",
                        "perturbation_type": None,
                    },
                )
                n_summaries += 1

        # upsert can update same external_id; report distinct counts from DB
        return {
            "files": [str(p) for p in files],
            "papers_loaded": n_papers,
            "summaries_loaded": n_summaries,
            "papers_in_db": db.count_papers(conn),
            "summaries_in_db": db.count_summaries(conn),
            "skipped_empty": skipped_empty,
            "db_path": str(config.DB_PATH),
        }
    finally:
        conn.close()


def main() -> None:
    reset = "--no-reset" not in sys.argv
    stats = load(reset=reset)
    print("[load] BioLaySumm → SQLite")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
