"""Headless EDA for the cleaned clinical notes.

Reads clinical/data/clinical.db and writes figures + a text report to
clinical/results/. Safe to run repeatedly.

Run:
    python -m clinical.src.eda
"""
from __future__ import annotations

import json
from collections import Counter

import matplotlib

matplotlib.use("Agg")  # headless backend; no display needed
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import config, db  # noqa: E402


def load_notes() -> pd.DataFrame:
    conn = db.connect()
    try:
        if db.count_notes(conn) == 0:
            raise SystemExit(
                "No notes found. Run `python -m clinical.src.load_mtsamples` first."
            )
        df = pd.read_sql_query("SELECT * FROM clinical_notes", conn)
    finally:
        conn.close()
    return df


def plot_specialties(df: pd.DataFrame) -> None:
    counts = df["medical_specialty"].value_counts().head(20)[::-1]
    plt.figure(figsize=(9, 8))
    plt.barh(counts.index, counts.values, color="#3b7dd8")
    plt.title("Top 20 medical specialties (note count)")
    plt.xlabel("Number of notes")
    plt.tight_layout()
    out = config.RESULTS_DIR / "eda_specialties.png"
    plt.savefig(out, dpi=120)
    plt.close()
    print(f"[eda] wrote {out}")


def plot_length_distribution(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].hist(df["word_count"], bins=50, color="#2ca089")
    axes[0].set_title("Note length (words)")
    axes[0].set_xlabel("words")
    axes[0].set_ylabel("notes")

    axes[1].hist(df["section_count"], bins=range(0, df["section_count"].max() + 2),
                 color="#d1793b", align="left")
    axes[1].set_title("Detected sections per note")
    axes[1].set_xlabel("section count")
    axes[1].set_ylabel("notes")
    plt.tight_layout()
    out = config.RESULTS_DIR / "eda_lengths.png"
    plt.savefig(out, dpi=120)
    plt.close()
    print(f"[eda] wrote {out}")


def top_section_headers(df: pd.DataFrame, top_n: int = 25) -> Counter:
    counter: Counter = Counter()
    for raw in df["sections_json"]:
        try:
            secs = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for header in secs:
            if header != "UNSECTIONED":
                counter[header] += 1
    return counter


def plot_top_headers(counter: Counter) -> None:
    common = counter.most_common(25)[::-1]
    if not common:
        print("[eda] no section headers detected; skipping header plot.")
        return
    labels = [h for h, _ in common]
    values = [c for _, c in common]
    plt.figure(figsize=(9, 9))
    plt.barh(labels, values, color="#8a5cd1")
    plt.title("Most common section headers")
    plt.xlabel("notes containing header")
    plt.tight_layout()
    out = config.RESULTS_DIR / "eda_section_headers.png"
    plt.savefig(out, dpi=120)
    plt.close()
    print(f"[eda] wrote {out}")


def write_report(df: pd.DataFrame, header_counter: Counter) -> None:
    lines = []
    lines.append("# CuraVerify Clinical — Day 1 EDA Report\n")
    lines.append(f"- Total notes: **{len(df)}**")
    lines.append(f"- Distinct specialties: **{df['medical_specialty'].nunique()}**")
    lines.append(f"- Words per note — median {int(df['word_count'].median())}, "
                 f"mean {df['word_count'].mean():.0f}, "
                 f"min {int(df['word_count'].min())}, max {int(df['word_count'].max())}")
    lines.append(f"- Sections per note — median {int(df['section_count'].median())}, "
                 f"mean {df['section_count'].mean():.1f}")
    n_unsectioned = int((df["section_count"] == 0).sum())
    lines.append(f"- Notes with no detected sections: **{n_unsectioned}** "
                 f"({100 * n_unsectioned / len(df):.1f}%)\n")

    lines.append("## Top 15 specialties\n")
    for spec, cnt in df["medical_specialty"].value_counts().head(15).items():
        lines.append(f"- {spec}: {cnt}")
    lines.append("")

    lines.append("## Top 20 section headers\n")
    for header, cnt in header_counter.most_common(20):
        lines.append(f"- {header}: {cnt}")
    lines.append("")

    out = config.RESULTS_DIR / "eda_report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[eda] wrote {out}")


def main() -> None:
    config.ensure_dirs()
    df = load_notes()
    print(f"[eda] loaded {len(df)} notes from {config.DB_PATH}")

    plot_specialties(df)
    plot_length_distribution(df)
    header_counter = top_section_headers(df)
    plot_top_headers(header_counter)
    write_report(df, header_counter)

    print("\n[eda] Done. See clinical/results/ for figures + eda_report.md")


if __name__ == "__main__":
    main()
