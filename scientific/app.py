"""CuraVerify Streamlit product demo — BioLaySumm faithfulness verification."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scientific.src import config, db  # noqa: E402
from scientific.src.aggregate import aggregate_verdicts  # noqa: E402
from scientific.src.verify import verify_summary_against_article  # noqa: E402

DEMO_SAMPLES_PATH = config.DATA_DIR / "demo_samples.json"
EVAL_METRICS_PATH = config.RESULTS_DIR / "eval_metrics.json"
EVAL_TABLE_PATH = config.RESULTS_DIR / "eval_table.md"

GRADE_COLORS = {
    "E1": "#1b7f4e",
    "E2": "#b8860b",
    "E3": "#c45c26",
    "E4": "#b42318",
}

VERDICT_COLORS = {
    "OK": "#1b7f4e",
    "SUSPICIOUS": "#b8860b",
    "LIKELY_HALLUCINATED": "#c45c26",
    "CONTAINS_CRITICAL_ERRORS": "#b42318",
}


def _load_demo_samples() -> List[Dict[str, Any]]:
    if not DEMO_SAMPLES_PATH.exists():
        return []
    data = json.loads(DEMO_SAMPLES_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _load_db_samples(limit: int = 30) -> List[Dict[str, Any]]:
    if not config.DB_PATH.exists():
        return []
    conn = db.connect()
    try:
        rows = conn.execute(
            """
            SELECT s.id, s.summary_text, s.is_real, s.perturbation_type,
                   p.title, p.article, p.source, p.id AS paper_id, p.sections_json
            FROM summaries s
            JOIN papers p ON p.id = s.paper_id
            ORDER BY s.is_real ASC, s.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["label"] = "REAL" if d.get("is_real") else "HALL"
            d["id"] = f"db-{d['id']}"
            out.append(d)
        return out
    finally:
        conn.close()


def _load_eval_metrics() -> Optional[Dict[str, Any]]:
    if not EVAL_METRICS_PATH.exists():
        return None
    return json.loads(EVAL_METRICS_PATH.read_text(encoding="utf-8"))


def _grade_badge(grade: str) -> str:
    color = GRADE_COLORS.get(grade, "#555")
    return (
        f"<span style='background:{color};color:#fff;padding:2px 8px;"
        f"border-radius:4px;font-weight:600;font-size:0.85rem'>{grade}</span>"
    )


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.2rem; max-width: 1200px; }
        h1 { letter-spacing: -0.02em; }
        .cura-hero {
            background: linear-gradient(135deg, #0f3d3e 0%, #1a5c4a 45%, #2d6a4f 100%);
            color: #f4f7f5;
            padding: 1.4rem 1.6rem;
            border-radius: 12px;
            margin-bottom: 1rem;
        }
        .cura-hero h1 { color: #fff !important; margin: 0 0 0.35rem 0; font-size: 1.85rem; }
        .cura-hero p { margin: 0; opacity: 0.92; font-size: 1.02rem; }
        .cura-metric-card {
            border: 1px solid #d8e2dc; border-radius: 10px; padding: 0.75rem 0.9rem;
            background: #f8faf9; text-align: center;
        }
        .cura-metric-card .label { font-size: 0.75rem; color: #5c6b66; text-transform: uppercase; }
        .cura-metric-card .value { font-size: 1.25rem; font-weight: 700; color: #1b4332; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="CuraVerify",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_styles()

    st.markdown(
        """
        <div class="cura-hero">
          <h1>CuraVerify</h1>
          <p>Paper-grounded scientific summary faithfulness — a CuraView (GraphRAG + E1–E4) port to BioLaySumm.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("CuraView stages")
        st.markdown(
            """
1. **Input** — article + lay summary  
2. **Segment** — sentences / claims  
3. **Evidence** — GraphRAG package  
4. **Judge** — hybrid verifier  
5. **Grade** — E1–E4 + type  
6. **Emit** — JSON + document verdict  
"""
        )
        method = st.selectbox("Retrieval method", ["graphrag", "flat"], index=0)
        source_mode = st.radio(
            "Sample source",
            ["Bundled demo samples", "Local database (optional)", "Paste your own"],
            index=0,
        )
        st.caption("Spaces use bundled samples — no SQLite or BioLaySumm download required.")

    tab_verify, tab_eval, tab_about = st.tabs(
        ["Verify summary", "Evaluation results", "How it works"]
    )

    with tab_verify:
        article = ""
        summary = ""
        paper_id = 0
        title = "Custom input"
        sections_json = "{}"

        if source_mode == "Bundled demo samples":
            samples = _load_demo_samples()
            if not samples:
                st.error(
                    f"Missing `{DEMO_SAMPLES_PATH.name}`. "
                    "Expected at scientific/data/demo_samples.json"
                )
                return
            labels = [
                f"[{s.get('label', 'SAMPLE')}] {s.get('title', 'Untitled')[:72]}"
                + (f" · {s['perturbation_type']}" if s.get("perturbation_type") else "")
                for s in samples
            ]
            choice = st.selectbox("Demo sample", labels)
            sel = samples[labels.index(choice)]
            article = sel.get("article") or ""
            summary = sel.get("summary_text") or ""
            paper_id = int(sel.get("paper_id") or 0)
            title = sel.get("title") or title
            sections_json = sel.get("sections_json") or "{}"
            meta = (
                f"**{sel.get('label')}** · source={sel.get('source')} · "
                f"perturbation={sel.get('perturbation_type') or 'none'}"
            )
            if sel.get("perturbation_note"):
                meta += f" · {sel['perturbation_note']}"
            st.info(meta)

        elif source_mode == "Local database (optional)":
            samples = _load_db_samples()
            if samples:
                labels = [
                    f"[{s.get('label')}] {s.get('title', '')[:70]} (id={s.get('id')})"
                    for s in samples
                ]
                choice = st.selectbox("Database sample", labels)
                sel = samples[labels.index(choice)]
                article = sel.get("article") or ""
                summary = sel.get("summary_text") or ""
                paper_id = int(sel.get("paper_id") or 0)
                title = sel.get("title") or title
                sections_json = sel.get("sections_json") or "{}"
                st.info(
                    f"Source={sel.get('source')} | real={bool(sel.get('is_real'))} | "
                    f"perturbation={sel.get('perturbation_type')}"
                )
            else:
                st.warning(
                    "No local DB. Use bundled demo samples, or run "
                    "`py -m scientific.run_pipeline` locally."
                )

        col1, col2 = st.columns(2)
        with col1:
            article = st.text_area("Source article (ground truth)", value=article, height=340)
        with col2:
            summary = st.text_area("Lay summary to verify", value=summary, height=340)

        run = st.button("Run verification", type="primary", use_container_width=False)

        if run:
            if not article.strip() or not summary.strip():
                st.error("Provide both article and summary.")
            else:
                with st.spinner("Running 6-stage pipeline (segment → GraphRAG → judge → grade)..."):
                    verdicts = verify_summary_against_article(
                        summary_text=summary,
                        article=article,
                        paper_id=paper_id,
                        title=title,
                        sections_json=sections_json,
                        method=method,
                    )
                    doc = aggregate_verdicts(0, verdicts, method=method)

                vcolor = VERDICT_COLORS.get(doc.overall_verdict, "#333")
                st.markdown("### Document verdict")
                m1, m2, m3, m4, m5 = st.columns(5)
                with m1:
                    st.markdown(
                        f"<div class='cura-metric-card'><div class='label'>Verdict</div>"
                        f"<div class='value' style='color:{vcolor};font-size:0.95rem'>"
                        f"{doc.overall_verdict}</div></div>",
                        unsafe_allow_html=True,
                    )
                for col, grade, count in (
                    (m2, "E1", doc.count_e1),
                    (m3, "E2", doc.count_e2),
                    (m4, "E3", doc.count_e3),
                    (m5, "E4", doc.count_e4),
                ):
                    with col:
                        st.markdown(
                            f"<div class='cura-metric-card'><div class='label'>{grade}</div>"
                            f"<div class='value' style='color:{GRADE_COLORS[grade]}'>{count}</div></div>",
                            unsafe_allow_html=True,
                        )

                st.markdown(
                    f"**Hallucination rate (E3+E4):** {doc.hallucination_rate:.1%} &nbsp;|&nbsp; "
                    f"**Contradiction rate (E4):** {doc.contradiction_rate:.1%}"
                )

                st.markdown("### Sentence-level results")
                rows = []
                for v in verdicts:
                    cite = v.citations[0].snippet if v.citations else ""
                    rows.append(
                        {
                            "idx": v.sentence_idx,
                            "grade": v.grade,
                            "type": v.hallucination_type or "—",
                            "confidence": round(v.confidence, 2),
                            "sentence": v.sentence_text,
                            "reasoning": v.reasoning,
                            "evidence": cite,
                        }
                    )
                df = pd.DataFrame(rows)
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "grade": st.column_config.TextColumn("Grade", width="small"),
                        "type": st.column_config.TextColumn("Type", width="medium"),
                        "confidence": st.column_config.NumberColumn("Conf.", format="%.2f"),
                        "sentence": st.column_config.TextColumn("Sentence", width="large"),
                        "reasoning": st.column_config.TextColumn("Reasoning", width="large"),
                        "evidence": st.column_config.TextColumn("Evidence snippet", width="large"),
                    },
                )

                # Grade legend
                legend = " ".join(_grade_badge(g) + f"&nbsp;{g}&nbsp;&nbsp;" for g in ("E1", "E2", "E3", "E4"))
                st.markdown(
                    "**Grades:** E1 strong support · E2 weak/paraphrase · E3 no support · E4 contradiction  \n"
                    + legend,
                    unsafe_allow_html=True,
                )

                with st.expander("Structured JSON (first sentence)"):
                    if verdicts:
                        st.json(json.loads(verdicts[0].model_dump_json()))

                try:
                    from scientific.src.verify import get_or_build_graph

                    G = get_or_build_graph(paper_id or 0, title, article, sections_json)
                    st.markdown("### Knowledge graph (stats)")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Nodes", G.number_of_nodes())
                    c2.metric("Edges", G.number_of_edges())
                    c3.write(G.graph.get("entity_counts", {}))
                except Exception as e:  # noqa: BLE001
                    st.caption(f"KG stats skipped: {e}")

    with tab_eval:
        st.subheader("Offline evaluation (BioLaySumm hall+real set)")
        st.caption(
            "Metrics from `scientific/results/` after `py -m scientific.run_pipeline`. "
            "Shows document-level hallucination detection (E3+E4) vs a flat-retrieval baseline."
        )
        metrics = _load_eval_metrics()
        if metrics:
            rows = []
            for method_name, m in metrics.items():
                h = m.get("hallucination_detection_E3E4", {})
                e4 = m.get("E4_detection_wrong_value", {})
                rows.append(
                    {
                        "Method": method_name,
                        "E3+E4 F1": round(h.get("f1", 0), 3),
                        "E3+E4 P": round(h.get("precision", 0), 3),
                        "E3+E4 R": round(h.get("recall", 0), 3),
                        "E4 F1": round(e4.get("f1", 0), 3),
                        "Type match": round(m.get("type_match_rate", 0), 3),
                        "N docs": m.get("n_docs", 0),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            if "graphrag" in metrics:
                gc = metrics["graphrag"].get("grade_counts", {})
                st.markdown("**GraphRAG grade distribution (sentence-level)**")
                gcols = st.columns(4)
                for i, g in enumerate(("E1", "E2", "E3", "E4")):
                    gcols[i].metric(g, gc.get(g, 0))
        elif EVAL_TABLE_PATH.exists():
            st.markdown(EVAL_TABLE_PATH.read_text(encoding="utf-8"))
        else:
            st.warning("No eval artifacts found. Run the pipeline locally to regenerate them.")

        if EVAL_TABLE_PATH.exists():
            with st.expander("Raw eval table (markdown)"):
                st.markdown(EVAL_TABLE_PATH.read_text(encoding="utf-8"))

    with tab_about:
        st.markdown(
            """
### What this proves (viva)

1. **Unstructured → structured:** lay-summary sentences become claim-level verdicts with citations.  
2. **Paper grounding:** a per-article knowledge graph + snippet retrieval (GraphRAG-style) supplies evidence.  
3. **Faithfulness grades:** CuraView **E1–E4** plus scientific hallucination types
   (`wrong_value`, `wrong_method`, `wrong_attribution`, `missing_context`, `invented_fact`).

### Mapping

| CuraView (clinical) | CuraVerify (this demo) |
|---|---|
| Discharge notes | BioLaySumm article + expert lay summary |
| Patient GraphRAG | Per-article KG + retrieval |
| LLM judge | Hybrid rules (+ optional LLM) |
| E1–E4 emission | Pydantic models + document verdict |

### Try this in the demo

- Pick a **[REAL]** sample — expect mostly **E1/E2**.  
- Pick a **[HALL]** sample (e.g. `wrong_value`) — expect **E3/E4** on the perturbed claim.  
- Or paste your own article + summary under **Paste your own**.

### References

- Ye et al., *CuraView* — SSRN 7065322 / arXiv:2605.03476  
- BioLaySumm shared task (BioNLP @ ACL)  
- Goldsack et al., *Making Science Simple* (EMNLP 2022)
"""
        )

    st.markdown("---")
    st.caption(
        "CuraVerify — domain port of CuraView to BioLaySumm. Offline hybrid verifier by default "
        "(set CURAVERIFY_LLM_API_KEY for optional LLM refinement)."
    )


# Streamlit runs the script top-to-bottom (`streamlit run app.py` / HF Spaces).
main()
