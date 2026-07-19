"""Stage 3 — GraphRAG-style evidence package assembly."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Set

import networkx as nx

from .extract_entities import extract_entities, entity_names


def _tokenize(text: str) -> Set[str]:
    return {t for t in re.findall(r"[a-z0-9%]+", text.lower()) if len(t) > 2}


def _overlap_score(query: str, passage: str) -> float:
    q = _tokenize(query)
    p = _tokenize(passage)
    if not q or not p:
        return 0.0
    inter = len(q & p)
    return inter / max(len(q), 1)


def retrieve_subgraph(G: nx.DiGraph, claim_text: str, hops: int = 2) -> nx.DiGraph:
    claim_ents = extract_entities(claim_text, max_entities=20)
    seeds: List[str] = []
    for etype, items in claim_ents.items():
        for e in items:
            nid = f"{etype}::{e['canonical']}"
            if nid in G:
                seeds.append(nid)
    # Fallback: match claim tokens against node names
    if not seeds:
        claim_toks = _tokenize(claim_text)
        for nid, data in G.nodes(data=True):
            name = str(data.get("canonical") or data.get("name") or "")
            if name and name in claim_text.lower():
                seeds.append(nid)
            elif name and any(tok in name for tok in claim_toks if len(tok) > 4):
                seeds.append(nid)
            if len(seeds) >= 12:
                break

    if not seeds:
        return G.subgraph([]).copy()

    nodes: Set[str] = set(seeds)
    frontier = set(seeds)
    for _ in range(hops):
        nxt: Set[str] = set()
        for n in frontier:
            if n not in G:
                continue
            for nb in list(G.successors(n)) + list(G.predecessors(n)):
                if nb not in nodes:
                    nodes.add(nb)
                    nxt.add(nb)
        frontier = nxt
    return G.subgraph(nodes).copy()


def top_snippets(article_or_paras, claim_text: str, k: int = 5) -> List[Dict[str, Any]]:
    if isinstance(article_or_paras, list):
        paras = article_or_paras
    else:
        paras = re.split(r"\n\s*\n+", str(article_or_paras))
        paras = [p.strip() for p in paras if len(p.strip()) > 40]
        if len(paras) < 3:
            text = str(article_or_paras)
            paras = [text[i : i + 400] for i in range(0, len(text), 400)]

    scored = []
    for i, p in enumerate(paras):
        s = _overlap_score(claim_text, p)
        if s > 0:
            scored.append((s, i, p))
    scored.sort(reverse=True)
    out = []
    for s, i, p in scored[:k]:
        out.append(
            {
                "section": "article",
                "paragraph_id": i,
                "snippet": p[:350].replace("\n", " "),
                "score": round(float(s), 4),
            }
        )
    return out


def build_evidence_package(
    G: nx.DiGraph,
    claim_text: str,
    article: str,
    hops: int = 2,
) -> Dict[str, Any]:
    sub = retrieve_subgraph(G, claim_text, hops=hops)
    paras = G.graph.get("paragraphs") or []
    snippets = top_snippets(paras or article, claim_text, k=5)

    evidence_nodes = []
    for nid, data in sub.nodes(data=True):
        evidence_nodes.append(
            {
                "id": nid,
                "type": data.get("type"),
                "name": data.get("name"),
                "context_snippet": data.get("context_snippet", ""),
            }
        )

    evidence_relations = []
    for u, v, data in sub.edges(data=True):
        evidence_relations.append(
            {
                "source": u,
                "target": v,
                "type": data.get("type", "related"),
                "evidence": (data.get("evidence") or "")[:160],
            }
        )

    # Simple chains: seed → neighbor → neighbor
    chains = []
    claim_ents = set(entity_names(extract_entities(claim_text, max_entities=15)))
    seeds = [
        n for n, d in sub.nodes(data=True)
        if d.get("canonical") in claim_ents or (d.get("name") or "").lower() in claim_text.lower()
    ][:5]
    for s in seeds:
        for nb in list(sub.successors(s))[:3]:
            chains.append([s, sub.edges[s, nb].get("type", "related"), nb])
            for nb2 in list(sub.successors(nb))[:2]:
                chains.append(
                    [
                        s,
                        sub.edges[s, nb].get("type", "related"),
                        nb,
                        sub.edges[nb, nb2].get("type", "related"),
                        nb2,
                    ]
                )
            if len(chains) >= 5:
                break
        if len(chains) >= 5:
            break

    return {
        "evidence_nodes": evidence_nodes[:40],
        "evidence_relations": evidence_relations[:60],
        "evidence_chains": chains[:5],
        "source_snippets": snippets,
        "n_subgraph_nodes": sub.number_of_nodes(),
        "n_subgraph_edges": sub.number_of_edges(),
    }
