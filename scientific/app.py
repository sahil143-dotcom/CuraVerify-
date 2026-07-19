"""CuraVerify Streamlit demo — BioLaySumm article ↔ lay-summary faithfulness."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scientific.src import config, db  # noqa: E402
from scientific.src.aggregate import aggregate_verdicts  # noqa: E402
from scientific.src.verify import verify_summary_against_article  # noqa: E402

st.set_page_config(page_title="CuraVerify", layout="wide")
st.title("CuraVerify — Scientific Faithfulness Verifier")
st.caption(
    "CuraView 6-stage port: article (source) → lay summary claims → E1–E4 evidence grades"
)

with st.sidebar:
    st.header("Pipeline stages")
    st.markdown(
        """
1. **Input** — article + summary  
2. **Segment** — sentences / claims  
3. **Evidence** — GraphRAG package  
4. **Judge** — hybrid verifier  
5. **Grade** — E1–E4 + type  
6. **Emit** — structured JSON + doc verdict  
"""
    )
    method = st.selectbox("Retrieval method", ["graphrag", "flat"])
    use_db = st.checkbox("Load sample from database", value=True)


def _load_samples(limit: int = 30):
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
        return [dict(r) for r in rows]
    finally:
        conn.close()


article = ""
summary = ""
paper_id = 0
title = ""
sections_json = "{}"

if use_db:
    samples = _load_samples()
    if samples:
        labels = [
            f"{'[HALL]' if not s['is_real'] else '[REAL]'} {s['title'][:70]} (id={s['id']})"
            for s in samples
        ]
        choice = st.selectbox("Sample", labels)
        sel = samples[labels.index(choice)]
        article = sel["article"]
        summary = sel["summary_text"]
        paper_id = sel["paper_id"]
        title = sel["title"]
        sections_json = sel["sections_json"] or "{}"
        st.info(
            f"Source={sel['source']} | real={bool(sel['is_real'])} | "
            f"perturbation={sel['perturbation_type']}"
        )
    else:
        st.warning("No DB samples. Run: `py -m scientific.run_pipeline`")

col1, col2 = st.columns(2)
with col1:
    article = st.text_area("Source article", value=article, height=320)
with col2:
    summary = st.text_area("Summary to verify", value=summary, height=320)

if st.button("Run verification", type="primary"):
    if not article.strip() or not summary.strip():
        st.error("Provide both article and summary.")
    else:
        with st.spinner("Running 6-stage pipeline..."):
            verdicts = verify_summary_against_article(
                summary_text=summary,
                article=article,
                paper_id=paper_id,
                title=title,
                sections_json=sections_json,
                method=method,
            )
            doc = aggregate_verdicts(0, verdicts, method=method)

        st.subheader("Document verdict")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Verdict", doc.overall_verdict)
        c2.metric("E1", doc.count_e1)
        c3.metric("E2", doc.count_e2)
        c4.metric("E3", doc.count_e3)
        c5.metric("E4", doc.count_e4)
        st.write(
            f"Hallucination rate: **{doc.hallucination_rate:.2%}** | "
            f"Contradiction rate: **{doc.contradiction_rate:.2%}**"
        )

        st.subheader("Sentence-level results")
        rows = []
        for v in verdicts:
            cite = v.citations[0].snippet if v.citations else ""
            rows.append(
                {
                    "idx": v.sentence_idx,
                    "grade": v.grade,
                    "type": v.hallucination_type or "",
                    "confidence": v.confidence,
                    "sentence": v.sentence_text[:180],
                    "reasoning": v.reasoning,
                    "evidence": cite[:160],
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

        with st.expander("Raw JSON (first sentence)"):
            if verdicts:
                st.json(json.loads(verdicts[0].model_dump_json()))

        # Lightweight KG stats
        try:
            from scientific.src.verify import get_or_build_graph

            G = get_or_build_graph(paper_id or 0, title, article, sections_json)
            st.subheader("Knowledge graph (stats)")
            st.write(
                {
                    "nodes": G.number_of_nodes(),
                    "edges": G.number_of_edges(),
                    "entity_counts": G.graph.get("entity_counts", {}),
                }
            )
        except Exception as e:  # noqa: BLE001
            st.caption(f"KG viz skipped: {e}")

st.markdown("---")
st.caption("CuraVerify — domain port of CuraView (SSRN 7065322) to BioLaySumm scientific summaries.")
