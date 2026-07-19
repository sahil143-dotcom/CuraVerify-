"""Stage 2 — per-paper Knowledge Graph construction (NetworkX)."""
from __future__ import annotations

import json
import pickle
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import networkx as nx

from . import config, db
from .extract_entities import extract_entities


def _paragraphs(article: str) -> List[str]:
    parts = re.split(r"\n\s*\n+", article)
    paras = [p.strip() for p in parts if len(p.strip()) > 40]
    if len(paras) < 3:
        # Fallback: chunk by ~500 chars
        paras = [article[i : i + 500].strip() for i in range(0, len(article), 500)]
        paras = [p for p in paras if p]
    return paras


def build_graph_for_article(
    paper_id: int,
    title: str,
    article: str,
    sections_json: str = "{}",
) -> nx.DiGraph:
    G = nx.DiGraph()
    G.graph["paper_id"] = paper_id
    G.graph["title"] = title

    try:
        sections = json.loads(sections_json or "{}")
    except json.JSONDecodeError:
        sections = {}

    headings = []
    if isinstance(sections.get("headings"), str):
        headings = [h.strip() for h in sections["headings"].split("|") if h.strip()]

    # Section nodes
    if headings:
        for h in headings[:30]:
            sid = f"section::{h.lower()}"
            G.add_node(sid, type="section", name=h)
    else:
        G.add_node("section::full", type="section", name="full")

    entities = extract_entities(article)
    paras = _paragraphs(article)
    G.graph["paragraphs"] = paras

    # Add entity nodes
    for etype, items in entities.items():
        for e in items:
            nid = f"{etype}::{e['canonical']}"
            G.add_node(
                nid,
                type=etype,
                name=e["name"],
                canonical=e["canonical"],
                context_snippet=e.get("context_snippet", ""),
            )

    # Link methods/datasets/metrics to sections (first section as default)
    section_ids = [n for n, d in G.nodes(data=True) if d.get("type") == "section"]
    default_section = section_ids[0] if section_ids else "section::full"

    for nid, data in list(G.nodes(data=True)):
        t = data.get("type")
        if t in ("method", "dataset", "metric", "concept", "result"):
            G.add_edge(default_section, nid, type="cited_by")

    # Method —uses→ Dataset, Result —reports→ Metric (co-occurrence in paragraphs)
    methods = [n for n, d in G.nodes(data=True) if d.get("type") == "method"]
    datasets = [n for n, d in G.nodes(data=True) if d.get("type") == "dataset"]
    metrics = [n for n, d in G.nodes(data=True) if d.get("type") == "metric"]
    results = [n for n, d in G.nodes(data=True) if d.get("type") == "result"]

    for para in paras[:80]:
        pl = para.lower()
        local_m = [m for m in methods if G.nodes[m]["canonical"] in pl]
        local_d = [d for d in datasets if G.nodes[d]["canonical"] in pl]
        local_met = [m for m in metrics if G.nodes[m]["canonical"] in pl]
        local_r = [r for r in results if G.nodes[r]["canonical"] in pl]
        for m in local_m:
            for d in local_d:
                G.add_edge(m, d, type="uses", evidence=para[:180])
            for r in local_r[:3]:
                G.add_edge(m, r, type="reports", evidence=para[:180])
        for r in local_r:
            for met in local_met:
                G.add_edge(r, met, type="reports", evidence=para[:180])
            for d in local_d:
                G.add_edge(r, d, type="evaluated_on", evidence=para[:180])

    G.graph["entity_counts"] = {t: len(entities[t]) for t in entities}
    return G


def save_graph(G: nx.DiGraph, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)


def load_graph(path: Path) -> nx.DiGraph:
    with path.open("rb") as f:
        return pickle.load(f)


def kg_path_for_paper(paper_id: int) -> Path:
    return config.KG_DIR / f"{paper_id}.gpickle"


def build_for_papers(limit: int = 200, sources: Optional[List[str]] = None) -> Dict[str, Any]:
    config.ensure_dirs()
    conn = db.connect()
    try:
        db.init_db(conn)
        q = "SELECT id, title, article, sections_json, source, split FROM papers"
        params: list = []
        if sources:
            placeholders = ",".join("?" * len(sources))
            q += f" WHERE source IN ({placeholders})"
            params.extend(sources)
        # Prefer validation splits first for the default 200 profile
        q += " ORDER BY CASE WHEN split LIKE '%validation%' THEN 0 ELSE 1 END, id ASC"
        q += " LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
    finally:
        conn.close()

    built = 0
    skipped = 0
    for row in rows:
        try:
            G = build_graph_for_article(
                paper_id=row["id"],
                title=row["title"],
                article=row["article"],
                sections_json=row["sections_json"] or "{}",
            )
            save_graph(G, kg_path_for_paper(row["id"]))
            built += 1
        except Exception as e:  # noqa: BLE001
            skipped += 1
            print(f"[kg] skip paper {row['id']}: {e}")

    return {"built": built, "skipped": skipped, "kg_dir": str(config.KG_DIR)}


def main() -> None:
    limit = config.DEFAULT_KG_LIMIT
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    stats = build_for_papers(limit=limit)
    print("[kg] done:", stats)


if __name__ == "__main__":
    main()
