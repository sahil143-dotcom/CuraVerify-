"""Stages 4–6 — hybrid claim verification + structured emission."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from . import config
from .build_kg import build_graph_for_article, kg_path_for_paper, load_graph
from .evidence_package import build_evidence_package, top_snippets
from .models import Citation, ClaimVerdict
from .segment import atomic_claims, split_sentences

_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(%|percent)?", re.IGNORECASE)


def _nums(text: str) -> List[Tuple[float, str]]:
    out = []
    for m in _NUM_RE.finditer(text):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        out.append((v, unit))
    return out


def _token_overlap(a: str, b: str) -> float:
    ta = {t for t in re.findall(r"[a-z0-9]+", a.lower()) if len(t) > 2}
    tb = {t for t in re.findall(r"[a-z0-9]+", b.lower()) if len(t) > 2}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), 1)


def _best_snippet_score(claim: str, snippets: List[dict]) -> Tuple[float, Optional[dict]]:
    if not snippets:
        return 0.0, None
    best = max(snippets, key=lambda s: float(s.get("score") or 0.0))
    return float(best.get("score") or 0.0), best


def _numeric_conflict(claim: str, evidence_text: str) -> Optional[Tuple[float, float]]:
    cnums = _nums(claim)
    enums = _nums(evidence_text)
    if not cnums or not enums:
        return None
    for cv, cu in cnums:
        for ev, eu in enums:
            # Same unit family (both % or both bare)
            if (bool(cu) != bool(eu)) and not (cu or eu):
                pass
            # Relative difference
            if ev == 0:
                continue
            rel = abs(cv - ev) / max(abs(ev), 1e-6)
            if rel >= 0.15 and abs(cv - ev) >= 1.0:
                return cv, ev
    return None


def hybrid_grade_sentence(
    sentence: str,
    evidence_package: Dict[str, Any],
) -> ClaimVerdict:
    snippets = evidence_package.get("source_snippets") or []
    evidence_text = " ".join(s.get("snippet", "") for s in snippets)
    score, best = _best_snippet_score(sentence, snippets)
    overlap = _token_overlap(sentence, evidence_text)

    conflict = _numeric_conflict(sentence, evidence_text)
    n_nodes = int(evidence_package.get("n_subgraph_nodes") or 0)

    grade = "E3"
    htype = "invented_fact"
    conf = 0.55
    reasoning = "No sufficient supporting evidence found in the article."

    if conflict:
        grade = "E4"
        htype = "wrong_value"
        conf = 0.85
        reasoning = (
            f"Numeric mismatch: claim has {conflict[0]} but evidence suggests {conflict[1]}."
        )
    elif score >= 0.45 or overlap >= 0.55:
        grade = "E1"
        htype = None
        conf = min(0.95, 0.6 + max(score, overlap) * 0.4)
        reasoning = "Claim is strongly supported by overlapping article snippets."
    elif score >= 0.22 or overlap >= 0.30 or n_nodes >= 3:
        grade = "E2"
        htype = None
        conf = 0.6
        reasoning = "Partial / paraphrased support from article evidence."
    elif score > 0.05:
        grade = "E3"
        htype = "missing_context"
        conf = 0.55
        reasoning = "Weak retrieval hit; claim lacks clear grounding."

    citations = []
    if best:
        citations.append(
            Citation(
                section=best.get("section", "article"),
                paragraph_id=int(best.get("paragraph_id") or 0),
                snippet=best.get("snippet", ""),
            )
        )
    elif snippets:
        s0 = snippets[0]
        citations.append(
            Citation(
                section=s0.get("section", "article"),
                paragraph_id=int(s0.get("paragraph_id") or 0),
                snippet=s0.get("snippet", ""),
            )
        )

    return ClaimVerdict(
        sentence_idx=0,
        sentence_text=sentence,
        grade=grade,  # type: ignore[arg-type]
        hallucination_type=htype,  # type: ignore[arg-type]
        citations=citations,
        reasoning=reasoning,
        confidence=conf,
        claims=atomic_claims(sentence),
        evidence_package=evidence_package,
    )


def _optional_llm_refine(verdict: ClaimVerdict, claim: str, evidence_package: Dict) -> ClaimVerdict:
    """Optional LLM path if CURAVERIFY_LLM_API_KEY / OPENAI_API_KEY is set."""
    api_key = os.environ.get("CURAVERIFY_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return verdict
    base = os.environ.get("CURAVERIFY_LLM_BASE", "https://api.openai.com/v1")
    model = os.environ.get("CURAVERIFY_LLM_MODEL", "gpt-4o-mini")
    try:
        import urllib.request

        prompt = (
            "You are a scientific-paper hallucination verifier. "
            "Given CLAIM and EVIDENCE, return JSON with keys: "
            "grade (E1|E2|E3|E4), hallucination_type (or null), reasoning, confidence (0-1).\n\n"
            f"CLAIM: {claim}\n\nEVIDENCE: {json.dumps(evidence_package.get('source_snippets', [])[:3])}"
        )
        body = json.dumps(
            {
                "model": model,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{base.rstrip('/')}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return ClaimVerdict(
            sentence_idx=verdict.sentence_idx,
            sentence_text=verdict.sentence_text,
            grade=parsed.get("grade", verdict.grade),
            hallucination_type=parsed.get("hallucination_type"),
            citations=verdict.citations,
            reasoning=parsed.get("reasoning", verdict.reasoning),
            confidence=float(parsed.get("confidence", verdict.confidence)),
            claims=verdict.claims,
            evidence_package=verdict.evidence_package,
        )
    except Exception:
        return verdict


def get_or_build_graph(paper_id: int, title: str, article: str, sections_json: str = "{}") -> nx.DiGraph:
    path = kg_path_for_paper(paper_id)
    if path.exists():
        return load_graph(path)
    G = build_graph_for_article(paper_id, title, article, sections_json)
    from .build_kg import save_graph

    save_graph(G, path)
    return G


def verify_summary_against_article(
    summary_text: str,
    article: str,
    paper_id: int = 0,
    title: str = "",
    sections_json: str = "{}",
    method: str = "graphrag",
) -> List[ClaimVerdict]:
    sentences = split_sentences(summary_text)
    if method == "flat":
        # Flat retrieval: no KG, snippets only
        verdicts = []
        for i, sent in enumerate(sentences):
            snippets = top_snippets(article, sent, k=5)
            ep = {
                "evidence_nodes": [],
                "evidence_relations": [],
                "evidence_chains": [],
                "source_snippets": snippets,
                "n_subgraph_nodes": 0,
                "n_subgraph_edges": 0,
            }
            v = hybrid_grade_sentence(sent, ep)
            v.sentence_idx = i
            v = _optional_llm_refine(v, sent, ep)
            verdicts.append(v)
        return verdicts

    G = get_or_build_graph(paper_id, title, article, sections_json)
    verdicts = []
    for i, sent in enumerate(sentences):
        ep = build_evidence_package(G, sent, article, hops=2)
        v = hybrid_grade_sentence(sent, ep)
        v.sentence_idx = i
        v = _optional_llm_refine(v, sent, ep)
        verdicts.append(v)
    return verdicts


def verdict_to_db_row(summary_id: int, v: ClaimVerdict, method: str) -> dict:
    return {
        "summary_id": summary_id,
        "sentence_idx": v.sentence_idx,
        "sentence_text": v.sentence_text,
        "grade": v.grade,
        "hallucination_type": v.hallucination_type,
        "citations_json": json.dumps([c.model_dump() for c in v.citations], ensure_ascii=False),
        "reasoning": v.reasoning,
        "confidence": v.confidence,
        "claims_json": json.dumps(v.claims, ensure_ascii=False),
        "evidence_package_json": json.dumps(v.evidence_package, ensure_ascii=False),
        "method": method,
    }
