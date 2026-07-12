# CuraVerify — Architecture (Deep Dive)

> 4-layer architecture adapted from CuraView (Ye et al., SSRN 7065322, Fig. 1) to scientific-paper hallucination detection. Simplifications: single verifier (CuraView used 3 agents), 5-type taxonomy (CuraView used 7).

---

## High-Level Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CuraVerify System                                │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ LAYER 1 — KNOWLEDGE ACQUISITION                              │     │
│  │                                                              │     │
│  │  Input:  arXiv paper.pdf                                     │     │
│  │  Sources per paper:                                          │     │
│  │    • Title + abstract (from arXiv API)                       │     │
│  │    • Section structure (intro / methods / results /          │     │
│  │      experiments / conclusion)                               │     │
│  │    • Figure & table captions                                 │     │
│  │    • Numeric values (auto-extracted)                         │     │
│  │    • Inline citations                                        │     │
│  │  Storage: SQLite `papers` table                              │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                              ↓                                          │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ LAYER 2 — KNOWLEDGE REPRESENTATION                           │     │
│  │                                                              │     │
│  │  Per-paper NetworkX DiGraph:                                 │     │
│  │                                                              │     │
│  │  Node types:                                                │     │
│  │    • Method       (BERT, RoBERTa, GPT-4, LoRA, ...)          │     │
│  │    • Dataset      (GLUE, SQuAD, ImageNet, ...)               │     │
│  │    • Metric       (accuracy, F1, BLEU, perplexity, ...)      │     │
│  │    • Result       (94.2% on GLUE, ...)                      │     │
│  │    • Claim        (atomic factual statement)                │     │
│  │    • Section      (intro, methods, results, ...)             │     │
│  │                                                              │     │
│  │  Edge types:                                                │     │
│  │    • uses           (Method → Dataset / Method)              │     │
│  │    • evaluated_on   (Method → Dataset, Result → Dataset)     │     │
│  │    • reports        (Result → Metric)                        │     │
│  │    • improves_over  (Result → Result)                        │     │
│  │    • contradicts    (Result → Claim, Claim → Claim)          │     │
│  │    • cited_by       (Section → Claim, Section → Reference)   │     │
│  │                                                              │     │
│  │  Domain customization (CuraView §6.3.3 inspired):           │     │
│  │    • Synonym canonicalization                               │     │
│  │    • Duplicate entity merging                               │     │
│  │    • Numeric format normalization                           │     │
│  │    • Metric name aliasing (acc ↔ accuracy)                  │     │
│  │                                                              │     │
│  │  Storage: per-paper .gpickle + HTML visualization (pyvis)    │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                              ↓                                          │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ LAYER 3 — EVIDENCE REASONING (GraphRAG + Reasoning)          │     │
│  │                                                              │     │
│  │  Pipeline (per abstract sentence):                           │     │
│  │                                                              │     │
│  │  ┌─────────────────────────────────────────────────────┐    │     │
│  │  │ 3.1 — CLAIM EXTRACTION                              │    │     │
│  │  │  Sentence → 1+ atomic claims                        │    │     │
│  │  │  Example:                                           │    │     │
│  │  │    "BERT achieves 94.2% on GLUE"                    │    │     │
│  │  │    → [Claim(subject=BERT, predicate=achieves,       │    │     │
│  │  │            object=94.2%, benchmark=GLUE)]           │    │     │
│  │  └─────────────────────────────────────────────────────┘    │     │
│  │                          ↓                                   │     │
│  │  ┌─────────────────────────────────────────────────────┐    │     │
│  │  │ 3.2 — GRAPH RETRIEVAL                               │    │     │
│  │  │  Given claim entities (BERT, GLUE), pull 1-2 hop    │    │     │
│  │  │  subgraph containing:                               │    │     │
│  │  │    • BERT node + its results                        │    │     │
│  │  │    • GLUE node + evaluations                        │    │     │
│  │  │    • All result nodes reachable from both           │    │     │
│  │  └─────────────────────────────────────────────────────┘    │     │
│  │                          ↓                                   │     │
│  │  ┌─────────────────────────────────────────────────────┐    │     │
│  │  │ 3.3 — EVIDENCE PATH DISCOVERY                       │    │     │
│  │  │  Find multi-hop evidence chains connecting claim    │    │     │
│  │  │  entities to specific result nodes                  │    │     │
│  │  │  Example path: BERT → evaluated_on → GLUE →         │    │     │
│  │  │                reports → accuracy=91.7%             │    │     │
│  │  └─────────────────────────────────────────────────────┘    │     │
│  │                          ↓                                   │     │
│  │  ┌─────────────────────────────────────────────────────┐    │     │
│  │  │ 3.4 — RELATION-AWARE REASONING                      │    │     │
│  │  │  Aggregate over relations considering:              │    │     │
│  │  │    • Temporal context (was X reported before Y?)   │    │     │
│  │  │    • Comparative context (vs. baseline)             │    │     │
│  │  │    • Negation handling ("X does NOT achieve Y")     │    │     │
│  │  │    • Scope (which method, which dataset variant)    │    │     │
│  │  └─────────────────────────────────────────────────────┘    │     │
│  │                          ↓                                   │     │
│  │  ┌─────────────────────────────────────────────────────┐    │     │
│  │  │ 3.5 — EVIDENCE PACKAGE ASSEMBLY                     │    │     │
│  │  │  Output:                                            │    │     │
│  │  │    {                                                │    │     │
│  │  │      evidence_nodes:    [...],                       │    │     │
│  │  │      evidence_relations:[...],                       │    │     │
│  │  │      evidence_chains:   [...],                       │    │     │
│  │  │      source_snippets:   [{section, paragraph,        │    │     │
│  │  │                           page, snippet, ts}],        │    │     │
│  │  │    }                                                │    │     │
│  │  └─────────────────────────────────────────────────────┘    │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                              ↓                                          │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ LAYER 4 — VERIFICATION (Single Agent)                       │     │
│  │                                                              │     │
│  │  ┌─────────────────────────────────────────────────────┐    │     │
│  │  │ Claim Verifier (LLM)                                │    │     │
│  │  │  Input:  claim + evidence package                   │     │
│  │  │  Output: {                                         │     │
│  │  │    grade:       E1 | E2 | E3 | E4,                  │     │
│  │  │    type:        1-of-5 hallucination taxonomy,     │     │
│  │  │    citations:   [{section, paragraph, snippet}],    │     │
│  │  │    reasoning:   "Paper Section 4.2 reports 91.7%,   │     │
│  │  │                  not 94.2%.",                       │     │
│  │  │    confidence:  0.0–1.0,                            │     │
│  │  │  }                                                 │     │
│  │  │  Built-in: grade-type consistency, numeric match    │     │
│  │  │            check, confidence threshold validation   │     │
│  │  └─────────────────────────────────────────────────────┘    │     │
│  │                          ↓                                   │     │
│  │  OUTPUT: Sentence-level verdict + Document-level summary    │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ DATA CURATION (error analysis, not fine-tuning)               │     │
│  │                                                              │     │
│  │  After verification:                                         │     │
│  │    • Store (claim, evidence, verdict) triples               │     │
│  │    • Flag low-confidence or inconsistent results             │     │
│  │    • Use for qualitative error analysis + prompt iteration   │     │
│  │                                                              │     │
│  │  Hallucination Generation Agent (for test data):              │     │
│  │    • Generate controlled hallucinations using 5-type         │     │
│  │      taxonomy                                                 │     │
│  │    • Ensure diversity and realism                            │     │
│  └──────────────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Layer 1 — Knowledge Acquisition: Details

### Input
- `paper.pdf` from arXiv (publicly available, free)
- Mix: cs.CL (NLP), cs.AI (AI), cs.LG (ML) — diversity for generalization

### Extraction Pipeline
1. **Metadata** (arXiv API):
   - Title, authors, abstract, categories, published date
2. **PDF → text** (`pymupdf` + `pymupdf4llm`):
   - Preserve section headers (regex + heuristics: numbered headings, ALL CAPS lines, large font)
   - Capture figure/table captions
   - Detect equations (skip, not useful for claim verification)
   - Detect inline citations `[1]`, `(Smith et al., 2020)` (extract but don't verify in v1)
3. **Numeric extraction** (regex):
   - Percentages: `94.2%`, `0.942`
   - Decimals: `3.14`, `1e-5`
   - Comparisons: `>`, `<`, `=`, `±`
4. **Storage**:
   ```sql
   CREATE TABLE papers (
     id INTEGER PRIMARY KEY,
     arxiv_id TEXT UNIQUE,
     title TEXT,
     authors TEXT,           -- JSON array
     categories TEXT,        -- JSON array
     published TEXT,
     sections_json TEXT,     -- {intro: "...", methods: "...", results: "..."}
     full_text TEXT,
     numeric_values TEXT,    -- JSON array of {value, context, section}
     citations TEXT,         -- JSON array of citation strings
     pdf_path TEXT
   );
   ```

### Output Schema
```python
{
  "arxiv_id": "2402.03300",
  "title": "...",
  "sections": {
    "intro": "...",
    "methods": "...",
    "results": "...",
    "experiments": "...",
    "conclusion": "..."
  },
  "numeric_values": [
    {"value": 94.2, "unit": "%", "context": "accuracy on GLUE", "section": "results"}
  ],
  "citations": ["Vaswani et al., 2017", "..."]
}
```

---

## Layer 2 — Knowledge Representation: Details

### Node Schema
```python
# Node types and required fields
{
  "type": "method",
  "name": "BERT-base",
  "aliases": ["bert-base", "BERT", "bert_base_uncased"],
  "section_first_mentioned": "methods",
  "mentions": [para_id, para_id, ...]
}

{
  "type": "dataset",
  "name": "GLUE",
  "aliases": ["General Language Understanding Evaluation"],
  "task_type": "nlp_benchmark",
  "section_first_mentioned": "experiments"
}

{
  "type": "metric",
  "name": "accuracy",
  "aliases": ["acc", "ACC"],
  "higher_is_better": True
}

{
  "type": "result",
  "value": 94.2,
  "unit": "%",
  "method": "BERT-base",        # → edge
  "dataset": "GLUE",            # → edge
  "metric": "accuracy",         # → edge
  "section": "results",
  "context_snippet": "..."
}

{
  "type": "claim",
  "text": "BERT-base achieves 94.2% accuracy on GLUE",
  "subject": "BERT-base",
  "predicate": "achieves",
  "object": 94.2,
  "evidence_section": "results",
  "grade": "E1"                 # assigned later by verifier
}

{
  "type": "section",
  "name": "results",
  "summary": "..."
}
```

### Edge Schema
```python
{
  "type": "uses",
  "source": method_node_id,
  "target": dataset_node_id,
  "evidence": "We evaluate BERT-base on GLUE..."
}

{
  "type": "evaluated_on",
  "source": result_node_id,
  "target": dataset_node_id
}

{
  "type": "reports",
  "source": result_node_id,
  "target": metric_node_id
}

{
  "type": "improves_over",
  "source": result_node_id,
  "target": result_node_id,
  "delta": 2.3,                 # percentage points
  "is_significant": True
}

{
  "type": "contradicts",
  "source": claim_node_id,
  "target": result_node_id,
  "reason": "value mismatch: 94.2 vs 91.7"
}
```

### Domain Customization (CuraView §6.3.3)

Three common problems in EHR-style KGs (translated to scientific KGs):

| CuraView (medical) | CuraVerify (scientific) | Fix |
|---|---|---|
| Excessive fragmentation of lab measurements | Same metric reported under different units (`acc` vs `accuracy` vs `%`) | Normalize via alias map |
| Duplicate patient nodes | Same method referenced by many name variants (`BERT-base` = `bert_base_uncased`) | Canonical name + alias set |
| Inconsistent clinical terminology | Same method paraphrased (`we use BERT` vs `BERT is employed`) | Section-aware canonicalization |

These changes produce a more compact, connected per-paper graph.

---

## Layer 3 — Evidence Reasoning: Details

### 3.1 Claim Extraction

**Input:** abstract sentence
**Output:** atomic claim(s)

LLM prompt:
```
You are extracting atomic factual claims from a sentence.
Each claim must express exactly ONE fact (subject, predicate, object).

Sentence: "BERT achieves 94.2% accuracy on GLUE, outperforming RoBERTa by 2.3 points."

Atomic claims:
[
  {subject: "BERT", predicate: "achieves_accuracy", object: "94.2%", dataset: "GLUE"},
  {subject: "BERT", predicate: "outperforms", object: "RoBERTa", by: "2.3 points", metric: "accuracy"}
]
```

### 3.2 Graph Retrieval

For each claim, identify entities in the claim (e.g., `BERT`, `GLUE`, `accuracy`).
Pull 1–2 hop subgraph containing those entities + their connected results/metrics/datasets.

```python
def retrieve_subgraph(kg, claim_entities, hops=2):
    seed_nodes = [n for n in kg.nodes if n in claim_entities]
    subgraph_nodes = set(seed_nodes)
    frontier = set(seed_nodes)
    for _ in range(hops):
        new_frontier = set()
        for node in frontier:
            neighbors = list(kg.neighbors(node)) + list(kg.predecessors(node))
            for n in neighbors:
                if n not in subgraph_nodes:
                    subgraph_nodes.add(n)
                    new_frontier.add(n)
        frontier = new_frontier
    return kg.subgraph(subgraph_nodes)
```

### 3.3 Evidence Path Discovery

Find all paths in the subgraph connecting claim subject to claim object:
```python
import networkx as nx
all_paths = list(nx.all_simple_paths(subgraph, source=subject_node, target=object_node, cutoff=4))
```

### 3.4 Relation-Aware Reasoning

Aggregate evidence with attention to:
- **Temporal:** "We first trained on X, then evaluated on Y"
- **Comparative:** "X outperforms Y by 2.3 points" — must verify both X and Y's values
- **Negation:** "X does NOT improve over Y" — must check polarity carefully
- **Scope:** "On subset Z" vs "Overall" — claim scope must match evidence scope

### 3.5 Evidence Package Assembly

```python
{
  "evidence_nodes": [
    {"id": "n1", "type": "method", "name": "BERT", ...},
    {"id": "n2", "type": "result", "value": 91.7, ...}
  ],
  "evidence_relations": [
    {"source": "n1", "target": "n2", "type": "reports"}
  ],
  "evidence_chains": [
    ["n1", "uses", "n3", "evaluated_on", "n2"]  # BERT → uses → GLUE → evaluated_on → 91.7%
  ],
  "source_snippets": [
    {"section": "results", "paragraph_id": 12, "page": 6, "snippet": "...BERT achieves 91.7% accuracy..."}
  ]
}
```

---

## Layer 4 — Verification: Details

### Verifier Prompt

```
You are verifying whether a claim is supported by evidence from a scientific paper.

CLAIM: {claim_text}

EVIDENCE PACKAGE:
{evidence_package_json}

TASK:
1. Determine evidence grade:
   - E1 (Strong support): claim is directly stated with matching specifics
   - E2 (Weak support): claim is paraphrased or has minor numeric differences (rounding)
   - E3 (No support): claim has no supporting evidence in the paper
   - E4 (Contradiction): paper explicitly states the opposite or a different value

2. Classify hallucination type (if E3 or E4):
   - wrong_method: claim attributes result to wrong method
   - wrong_value: numeric value differs from paper
   - wrong_attribution: claim misattributes finding to wrong source
   - missing_context: claim omits important qualifiers
   - invented_fact: paper does not contain this fact at all

3. Cite supporting evidence (section, paragraph, snippet).
4. Provide one-sentence reasoning.
5. Estimate confidence 0.0–1.0.

OUTPUT (JSON only):
{
  "grade": "E1" | "E2" | "E3" | "E4",
  "type": "..." | null,
  "citations": [{"section": "...", "paragraph_id": ..., "snippet": "..."}],
  "reasoning": "...",
  "confidence": 0.0–1.0
}
```

### Built-in Consistency Checks

- If `grade == "E1"`, then `type` must be `null`
- If claim contains a number, citation snippet must contain a number
- If `type == "wrong_value"`, cited snippet must show a different number
- E4 verdicts should have confidence ≥ 0.7
- If a check fails, the verifier re-runs with a note to fix the inconsistency

---

## Data Curation (Error Analysis)

```
   ┌──────────────────────┐
   │  Hallucination Gen   │
   │  Agent               │
   │  (uses 5-type tax)   │
   └──────────┬───────────┘
              ↓
   ┌──────────────────────┐
   │  Verifier            │
   │  (assigns E1–E4)     │
   └──────────┬───────────┘
              ↓
   ┌──────────────────────┐
   │  Quality Control     │
   │  (consistency rules) │
   └──────────┬───────────┘
              ↓
   ┌──────────────────────┐
   │  Error Analysis      │
   │  → Improve prompts   │
   └──────────────────────┘
```

---

## Configuration (`config.yaml`)

```yaml
project:
  name: CuraVerify
  version: 0.1.0
  domain: scientific_papers

data:
  arxiv_categories: [cs.CL, cs.AI, cs.LG]
  num_papers: 50
  train_test_split: 0.8

kg:
  node_types: [method, dataset, metric, result, claim, section]
  edge_types: [uses, evaluated_on, reports, improves_over, contradicts, cited_by]
  normalization:
    - synonym_canonicalization: true
    - duplicate_merging: true
    - metric_aliasing: true

verification:
  llm_model: minimax-M3
  hops_in_subgraph: 2
  max_evidence_chains: 5
  evidence_grades: [E1, E2, E3, E4]
  hallucination_types:
    - wrong_method
    - wrong_value
    - wrong_attribution
    - missing_context
    - invented_fact

evaluation:
  held_out_papers: 10
  primary_metric: E4_F1
  secondary_metrics: [precision, recall, accuracy, type_wise_F1]
  baselines:
    - flat_retrieval_RAGTruth_style
    - flat_retrieval_QAGS_style
```