"""Evaluation: GraphRAG vs flat retrieval on E3+E4 / E4 detection."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

from . import config, db
from .aggregate import aggregate_verdicts, document_verdict_to_db_row
from .verify import verdict_to_db_row, verify_summary_against_article


def _prf(tp: int, fp: int, fn: int) -> Dict[str, float]:
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def run_verification_batch(
    limit: int = 50,
    methods: Tuple[str, ...] = ("graphrag", "flat"),
    clear_prior: bool = True,
) -> dict:
    config.ensure_dirs()
    conn = db.connect()
    try:
        db.init_db(conn)
        if clear_prior:
            conn.execute("DELETE FROM verification_results")
            conn.execute("DELETE FROM document_verdicts")
            conn.commit()

        # Half real, half hallucinated when possible
        hall = conn.execute(
            """
            SELECT s.id AS summary_id, s.summary_text, s.is_real, s.perturbation_type,
                   p.id AS paper_id, p.title, p.article, p.sections_json
            FROM summaries s
            JOIN papers p ON p.id = s.paper_id
            WHERE s.is_real = 0
            ORDER BY s.id
            LIMIT ?
            """,
            (limit // 2 + limit % 2,),
        ).fetchall()
        real = conn.execute(
            """
            SELECT s.id AS summary_id, s.summary_text, s.is_real, s.perturbation_type,
                   p.id AS paper_id, p.title, p.article, p.sections_json
            FROM summaries s
            JOIN papers p ON p.id = s.paper_id
            WHERE s.is_real = 1
            ORDER BY s.id
            LIMIT ?
            """,
            (limit // 2,),
        ).fetchall()
        rows = list(hall) + list(real)
        if not rows:
            raise SystemExit("No summaries to evaluate. Run load + hallucinate first.")

        processed = 0
        for row in rows:
            for method in methods:
                verdicts = verify_summary_against_article(
                    summary_text=row["summary_text"],
                    article=row["article"],
                    paper_id=row["paper_id"],
                    title=row["title"] or "",
                    sections_json=row["sections_json"] or "{}",
                    method=method,
                )
                db_rows = [verdict_to_db_row(row["summary_id"], v, method) for v in verdicts]
                db.insert_verification_rows(conn, db_rows)
                dv = aggregate_verdicts(row["summary_id"], verdicts, method=method)
                db.insert_document_verdict(conn, document_verdict_to_db_row(dv))
            processed += 1

        return {"processed_summaries": processed, "methods": list(methods)}
    finally:
        conn.close()


def compute_metrics() -> dict:
    """Document-level: gold hallucinated = is_real==0; predicted = any E3/E4."""
    conn = db.connect()
    try:
        methods = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT method FROM document_verdicts"
            ).fetchall()
        ]
        out: Dict[str, dict] = {}
        for method in methods:
            rows = conn.execute(
                """
                SELECT s.is_real, s.perturbation_type,
                       d.count_e3, d.count_e4, d.hallucination_rate, d.overall_verdict
                FROM document_verdicts d
                JOIN summaries s ON s.id = d.summary_id
                WHERE d.method = ?
                """,
                (method,),
            ).fetchall()

            # Hallucination detection (E3+E4)
            tp = fp = fn = tn = 0
            # E4 detection: gold = hallucinated with wrong_value; pred = count_e4>0
            e4_tp = e4_fp = e4_fn = 0
            type_correct = 0
            type_total = 0
            grade_counts = Counter()

            for r in rows:
                gold_hall = int(r["is_real"]) == 0
                pred_hall = (int(r["count_e3"]) + int(r["count_e4"])) > 0
                if gold_hall and pred_hall:
                    tp += 1
                elif not gold_hall and pred_hall:
                    fp += 1
                elif gold_hall and not pred_hall:
                    fn += 1
                else:
                    tn += 1

                gold_e4 = gold_hall and (r["perturbation_type"] == "wrong_value")
                pred_e4 = int(r["count_e4"]) > 0
                if gold_e4 and pred_e4:
                    e4_tp += 1
                elif not gold_e4 and pred_e4:
                    e4_fp += 1
                elif gold_e4 and not pred_e4:
                    e4_fn += 1

            # Sentence grades distribution
            for g, c in conn.execute(
                """
                SELECT grade, COUNT(*) FROM verification_results
                WHERE method = ? GROUP BY grade
                """,
                (method,),
            ).fetchall():
                grade_counts[g] = c

            # Type match among hallucinated docs: any E3/E4 sentence with matching type
            hall_docs = conn.execute(
                """
                SELECT s.id, s.perturbation_type
                FROM summaries s
                JOIN document_verdicts d ON d.summary_id = s.id
                WHERE s.is_real = 0 AND d.method = ?
                """,
                (method,),
            ).fetchall()
            for hd in hall_docs:
                ptype = hd["perturbation_type"]
                if not ptype:
                    continue
                type_total += 1
                hit = conn.execute(
                    """
                    SELECT 1 FROM verification_results
                    WHERE summary_id = ? AND method = ?
                      AND hallucination_type = ?
                      AND grade IN ('E3','E4')
                    LIMIT 1
                    """,
                    (hd["id"], method, ptype),
                ).fetchone()
                if hit:
                    type_correct += 1

            out[method] = {
                "n_docs": len(rows),
                "hallucination_detection_E3E4": _prf(tp, fp, fn),
                "E4_detection_wrong_value": _prf(e4_tp, e4_fp, e4_fn),
                "type_match_rate": round(type_correct / type_total, 4) if type_total else 0.0,
                "grade_counts": dict(grade_counts),
                "confusion_doc": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            }
        return out
    finally:
        conn.close()


def write_results(metrics: dict) -> Path:
    config.ensure_dirs()
    path = config.RESULTS_DIR / "eval_metrics.json"
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    # Markdown table
    md = ["# CuraVerify Evaluation Results", ""]
    md.append("| Method | E3+E4 F1 | E3+E4 P | E3+E4 R | E4 F1 | Type match | N |")
    md.append("|---|---:|---:|---:|---:|---:|---:|")
    for method, m in metrics.items():
        h = m["hallucination_detection_E3E4"]
        e4 = m["E4_detection_wrong_value"]
        md.append(
            f"| {method} | {h['f1']:.3f} | {h['precision']:.3f} | {h['recall']:.3f} | "
            f"{e4['f1']:.3f} | {m['type_match_rate']:.3f} | {m['n_docs']} |"
        )
    md.append("")
    md_path = config.RESULTS_DIR / "eval_table.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    # CSV
    csv_path = config.RESULTS_DIR / "eval_metrics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "method",
                "e3e4_f1",
                "e3e4_precision",
                "e3e4_recall",
                "e4_f1",
                "type_match_rate",
                "n_docs",
            ]
        )
        for method, m in metrics.items():
            h = m["hallucination_detection_E3E4"]
            e4 = m["E4_detection_wrong_value"]
            w.writerow(
                [
                    method,
                    h["f1"],
                    h["precision"],
                    h["recall"],
                    e4["f1"],
                    m["type_match_rate"],
                    m["n_docs"],
                ]
            )
    return md_path


def main() -> None:
    limit = config.DEFAULT_EVAL_N
    skip_run = "--metrics-only" in sys.argv
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    if not skip_run:
        print("[eval] running verification batch ...")
        print(run_verification_batch(limit=limit))
    metrics = compute_metrics()
    path = write_results(metrics)
    print("[eval] metrics:", json.dumps(metrics, indent=2))
    print("[eval] wrote", path)


if __name__ == "__main__":
    main()
