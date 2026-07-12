# CuraVerify — Data Schema Reference

> SQLite + JSON schemas for papers, abstracts, knowledge graphs, and verification outputs.

---

## 1. SQLite Schema

### Table: `papers`

Stores raw paper metadata + extracted text.

```sql
CREATE TABLE papers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arxiv_id        TEXT UNIQUE NOT NULL,         -- e.g. "2402.03300"
    title           TEXT NOT NULL,
    authors         TEXT NOT NULL,                 -- JSON array
    categories      TEXT NOT NULL,                 -- JSON array
    published       TEXT NOT NULL,                 -- ISO date YYYY-MM-DD
    pdf_path        TEXT NOT NULL,                 -- local file path
    sections_json   TEXT NOT NULL,                 -- JSON object: {intro, methods, results, ...}
    full_text       TEXT NOT NULL,                 -- concatenated text
    numeric_values  TEXT,                          -- JSON array of {value, unit, context, section}
    citations       TEXT,                          -- JSON array of citation strings
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Example row:**
```json
{
  "id": 1,
  "arxiv_id": "2402.03300",
  "title": "Example Paper Title",
  "authors": ["Alice Smith", "Bob Jones"],
  "categories": ["cs.CL", "cs.AI"],
  "published": "2024-02-05",
  "pdf_path": "data/raw_pdfs/2402.03300.pdf",
  "sections_json": "{\"intro\":\"...\",\"methods\":\"...\",\"results\":\"...\"}",
  "full_text": "...",
  "numeric_values": "[{\"value\":94.2,\"unit\":\"%\",\"context\":\"accuracy on GLUE\",\"section\":\"results\"}]",
  "citations": "[\"Vaswani et al., 2017\", ...]"
}
```

### Table: `abstracts`

Stores real + hallucinated abstracts for verification testing.

```sql
CREATE TABLE abstracts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        INTEGER NOT NULL,
    abstract_text   TEXT NOT NULL,                 -- the abstract content
    is_real         INTEGER NOT NULL,              -- 1 = real arxiv abstract, 0 = hallucinated
    source          TEXT,                          -- "arxiv_meta" | "llm_rewritten" | "human_rewritten"
    perturbation_type TEXT,                        -- if hallucinated, which of 5 types was applied
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paper_id) REFERENCES papers(id)
);
```

**Perturbation types** (matching 5-type hallucination taxonomy):
- `real` — original arXiv abstract
- `wrong_method` — replaced method name with different method
- `wrong_value` — changed numeric result
- `wrong_attribution` — changed attribution
- `missing_context` — removed important qualifiers
- `invented_fact` — added claim not in paper

### Table: `verification_results`

Stores verifier output per abstract sentence.

```sql
CREATE TABLE verification_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    abstract_id     INTEGER NOT NULL,
    sentence_idx    INTEGER NOT NULL,              -- 0-based sentence index
    sentence_text   TEXT NOT NULL,
    grade           TEXT NOT NULL,                 -- E1 | E2 | E3 | E4
    hallucination_type TEXT,                       -- 1-of-7 or NULL if E1
    citations_json  TEXT,                          -- JSON array of {section, paragraph_id, snippet}
    reasoning       TEXT,
    confidence      REAL,                          -- 0.0–1.0
    claims_json     TEXT,                          -- JSON array of atomic claims
    evidence_package_json TEXT,                    -- JSON object (evidence nodes/relations/chains/snippets)
    verified_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (abstract_id) REFERENCES abstracts(id)
);
```

### Table: `document_verdicts`

Stores aggregated per-document summary.

```sql
CREATE TABLE document_verdicts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    abstract_id     INTEGER NOT NULL,
    total_sentences INTEGER NOT NULL,
    count_e1        INTEGER NOT NULL,
    count_e2        INTEGER NOT NULL,
    count_e3        INTEGER NOT NULL,
    count_e4        INTEGER NOT NULL,
    hallucination_rate REAL,                       -- (E3 + E4) / total
    contradiction_rate REAL,                       -- E4 / total
    overall_verdict TEXT,                          -- "OK" | "SUSPICIOUS" | "LIKELY_HALLUCINATED"
    FOREIGN KEY (abstract_id) REFERENCES abstracts(id)
);
```

---

## 2. Knowledge Graph Schema (NetworkX)

Stored as `.gpickle` files. One per paper.

### Node Attributes

```python
# Method node
{
    "type": "method",
    "name": "BERT-base",
    "aliases": ["bert-base", "BERT", "bert_base_uncased"],
    "section_first_mentioned": "methods",
    "mention_count": 12
}

# Dataset node
{
    "type": "dataset",
    "name": "GLUE",
    "aliases": ["General Language Understanding Evaluation"],
    "task_type": "nlp_benchmark",
    "section_first_mentioned": "experiments",
    "mention_count": 8
}

# Metric node
{
    "type": "metric",
    "name": "accuracy",
    "aliases": ["acc", "ACC"],
    "higher_is_better": True,
    "mention_count": 15
}

# Result node
{
    "type": "result",
    "value": 94.2,
    "unit": "%",
    "method_name": "BERT-base",
    "dataset_name": "GLUE",
    "metric_name": "accuracy",
    "section": "results",
    "context_snippet": "Our BERT-base model achieves 94.2% accuracy on GLUE",
    "page": 6
}

# Claim node (added by Layer 3 after claim extraction)
{
    "type": "claim",
    "text": "BERT-base achieves 94.2% accuracy on GLUE",
    "subject": "BERT-base",
    "predicate": "achieves_accuracy",
    "object": "94.2%",
    "source_sentence": "Sentence from abstract...",
    "grade": "E1",  # assigned by verifier
    "hallucination_type": None  # assigned by verifier
}

# Section node
{
    "type": "section",
    "name": "results",
    "summary": "We present our main experimental results...",
    "paragraph_count": 8
}
```

### Edge Attributes

```python
# uses edge (Method → Dataset or Method → Method)
{
    "type": "uses",
    "evidence": "We evaluate BERT-base on GLUE",
    "section": "experiments"
}

# evaluated_on edge (Result → Dataset)
{
    "type": "evaluated_on",
    "section": "results"
}

# reports edge (Result → Metric)
{
    "type": "reports",
    "section": "results"
}

# improves_over edge (Result → Result)
{
    "type": "improves_over",
    "delta": 2.3,
    "delta_unit": "percentage_points",
    "is_significant": True,
    "evidence": "BERT-base improves over RoBERTa by 2.3 points (p < 0.05)"
}

# contradicts edge (Claim → Result)
{
    "type": "contradicts",
    "reason": "value_mismatch",
    "claim_value": 94.2,
    "paper_value": 91.7,
    "section": "results"
}

# cited_by edge (Section → Claim or Section → Reference)
{
    "type": "cited_by",
    "citation_string": "Vaswani et al., 2017"
}
```

### Example Graph (mini)

```
[methods: BERT-base] --uses--> [GLUE]
[BERT-base] --uses--> [RoBERTa]
[BERT-base] --reports--> [accuracy=91.7% on GLUE]
[RoBERTa] --reports--> [accuracy=89.4% on GLUE]
[BERT-base] --improves_over--> [RoBERTa] (delta=2.3)
[Claim: "BERT-base achieves 94.2% accuracy on GLUE"] --contradicts--> [accuracy=91.7%]
```

---

## 3. Verification Output JSON Schema

### Sentence-Level Output

```json
{
  "sentence_idx": 0,
  "sentence_text": "We propose a novel attention mechanism that achieves 94.2% accuracy on GLUE.",
  "claims": [
    {
      "claim_text": "model achieves 94.2% accuracy on GLUE",
      "subject": "model",
      "predicate": "achieves_accuracy",
      "object": "94.2%",
      "dataset": "GLUE"
    }
  ],
  "grade": "E4",
  "hallucination_type": "wrong_value",
  "citations": [
    {
      "section": "results",
      "paragraph_id": 12,
      "page": 6,
      "snippet": "Our model achieves 91.7% accuracy on GLUE."
    }
  ],
  "reasoning": "Abstract claims 94.2% but paper Section 4.2 reports 91.7%.",
  "confidence": 0.92,
  "evidence_package": {
    "evidence_nodes": [
      {"id": "n_method", "type": "method", "name": "model"},
      {"id": "n_glue", "type": "dataset", "name": "GLUE"},
      {"id": "n_result", "type": "result", "value": 91.7, "unit": "%"}
    ],
    "evidence_relations": [
      {"source": "n_method", "target": "n_glue", "type": "uses"},
      {"source": "n_result", "target": "n_glue", "type": "evaluated_on"},
      {"source": "n_result", "target": "n_method", "type": "reports"}
    ],
    "evidence_chains": [
      ["n_method", "uses", "n_glue", "evaluated_on", "n_result"]
    ],
    "source_snippets": [
      {
        "section": "results",
        "paragraph_id": 12,
        "page": 6,
        "snippet": "Our model achieves 91.7% accuracy on GLUE.",
        "timestamp": "2024-02-05T00:00:00Z"
      }
    ]
  }
}
```

### Document-Level Output

```json
{
  "paper_id": 1,
  "arxiv_id": "2402.03300",
  "abstract_id": 1,
  "total_sentences": 8,
  "counts": {
    "E1": 3,
    "E2": 2,
    "E3": 2,
    "E4": 1
  },
  "hallucination_rate": 0.375,
  "contradiction_rate": 0.125,
  "by_type": {
    "wrong_value": 1,
    "invented_fact": 1,
    "missing_context": 1
  },
  "overall_verdict": "LIKELY_HALLUCINATED",
  "verdict_reasoning": "Contains 1 direct contradiction (E4) and 2 unsupported claims (E3)."
}
```

---

## 4. File Layout

```
data/
├── papers.db                          ← SQLite database
├── papers_metadata.json               ← arXiv metadata dump
├── raw_pdfs/                          ← downloaded PDFs
│   ├── 2402.03300.pdf
│   ├── 2401.12345.pdf
│   └── ...
├── processed/                         ← extracted text + sections
│   ├── 2402.03300.json
│   └── ...
├── abstracts/                         ← abstract test sets
│   ├── real_abstracts.json            ← list of {arxiv_id, text}
│   ├── hallucinated_abstracts.json    ← list of {arxiv_id, text, perturbation_type}
│   └── abstract_pairs.json            ← (real, hallucinated) pairs for same paper
├── knowledge_graphs/                  ← per-paper KGs
│   ├── 2402.03300.gpickle
│   └── ...
└── verification_outputs/              ← verifier results
    ├── 2402.03300_real.json
    ├── 2402.03300_hallucinated.json
    └── ...
```