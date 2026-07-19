"""Heuristic scientific entity extraction (no LLM required for v1)."""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List

# Common metric / method / dataset cues
_METRIC_RE = re.compile(
    r"\b(accuracy|precision|recall|f1(?:-score)?|auc|auroc|bleu|rouge|perplexity|"
    r"sensitivity|specificity|pvalue|p-value|odds ratio|hazard ratio|"
    r"mean|median|correlation|r\^2|rmse|mae)\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*(%|percent|fold|×|x)?\b",
    re.IGNORECASE,
)
_METHOD_RE = re.compile(
    r"\b((?:CRISPR|RNA-seq|ChIP-seq|GWAS|PCR|ELISA|Western blot|qPCR|"
    r"BERT|RoBERTa|GPT-\d|Transformer|LoRA|CNN|RNN|LSTM|SVM|"
    r"random forest|logistic regression|ANOVA|t-test|Mann-Whitney)"
    r"(?:\s+[A-Za-z0-9\-+]+){0,2})\b",
    re.IGNORECASE,
)
_DATASET_RE = re.compile(
    r"\b((?:ImageNet|GLUE|SQuAD|CIFAR-?\d*|MIMIC(?:-III|-IV)?|TCGA|"
    r"UK Biobank|Gene Ontology|PubMed|GEO|ArrayExpress)"
    r"(?:\s+[A-Za-z0-9\-_]+){0,2})\b",
    re.IGNORECASE,
)
# Capitalized multi-word scientific phrases (lightweight NER)
_CAP_PHRASE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b"
)
_STOP = {
    "The", "This", "These", "Those", "There", "Here", "Figure", "Table",
    "Results", "Discussion", "Introduction", "Abstract", "Materials",
    "Methods", "Supplementary", "However", "Therefore", "Although",
}


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def extract_entities(text: str, max_entities: int = 80) -> Dict[str, List[dict]]:
    entities: Dict[str, List[dict]] = {
        "method": [],
        "dataset": [],
        "metric": [],
        "result": [],
        "concept": [],
    }
    seen = set()

    def add(etype: str, name: str, snippet: str = ""):
        key = (etype, _norm(name))
        if not name or key in seen:
            return
        seen.add(key)
        entities[etype].append(
            {
                "type": etype,
                "name": name.strip(),
                "canonical": _norm(name),
                "context_snippet": snippet[:200],
            }
        )

    for m in _METHOD_RE.finditer(text):
        add("method", m.group(1), text[max(0, m.start() - 40) : m.end() + 40])
    for m in _DATASET_RE.finditer(text):
        add("dataset", m.group(1), text[max(0, m.start() - 40) : m.end() + 40])
    for m in _METRIC_RE.finditer(text):
        add("metric", m.group(1), text[max(0, m.start() - 40) : m.end() + 40])

    for m in _NUMBER_RE.finditer(text):
        val = m.group(1)
        unit = (m.group(2) or "").strip()
        ctx = text[max(0, m.start() - 50) : m.end() + 50].replace("\n", " ")
        name = f"{val}{unit}" if unit else val
        add("result", name, ctx)

    # Top capitalized concepts (frequency-capped)
    caps = [
        p for p in _CAP_PHRASE.findall(text)
        if p.split()[0] not in _STOP and len(p) > 5
    ]
    for name, _cnt in Counter(caps).most_common(25):
        add("concept", name)

    # Cap total
    total = 0
    capped: Dict[str, List[dict]] = {k: [] for k in entities}
    for etype in ("method", "dataset", "metric", "result", "concept"):
        for e in entities[etype]:
            if total >= max_entities:
                break
            capped[etype].append(e)
            total += 1
    return capped


def entity_names(entities: Dict[str, List[dict]]) -> List[str]:
    names = []
    for etype in entities:
        for e in entities[etype]:
            names.append(e["canonical"])
    return names
