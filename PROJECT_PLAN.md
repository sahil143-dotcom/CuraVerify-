# CuraVerify — Project Plan

> **Domain port of CuraView (Ye et al., SSRN 7065322) to scientific-paper hallucination detection.**
> Patient-grounded claim verification → Paper-grounded claim verification.

---

## 1. Problem Statement

Given a **source document** (scientific paper full text) and a **generated summary** (abstract — real or AI-rewritten), automatically detect which sentences in the summary are **unsupported or contradicted** by the source, and explain *why* with a citation-style traceback.

### Input / Output

```
INPUT:
  - paper.pdf (full text, ~8–15 pages)
  - abstract.txt (8–12 sentences, may be real or AI-generated)

OUTPUT (per sentence):
  {
    "sentence":   "Our model achieves 94.2% accuracy on GLUE.",
    "grade":      "E1" | "E2" | "E3" | "E4",
    "type":       "wrong_method" | "wrong_value" | "wrong_attribution" | "missing_context" | "invented_fact" | null,
    "evidence":   [ {section, paragraph, snippet} ],
    "reasoning":  "The paper Section 4.2 reports 91.7% on GLUE, not 94.2%.",
    "confidence": 0.0–1.0
  }

OUTPUT (document-level):
  {
    "paper_id":         "2402.03300",
    "total_sentences":  10,
    "counts":           {"E1": 4, "E2": 2, "E3": 3, "E4": 1},
    "hallucination_rate": 0.40,
    "overall_verdict":  "Likely contains hallucinations — 1 contradiction, 3 unsupported claims."
  }
```

### Evidence Grading (E1–E4, from CuraView)

| Grade | Meaning | Clinical analog | Our analog |
|---|---|---|---|
| **E1** | Strong support | Statement exactly matches chart field | Claim directly stated in paper text |
| **E2** | Weak support | Paraphrase, partial match | Claim is paraphrased / numerical rounding |
| **E3** | No support | Not in record | Claim absent from paper |
| **E4** | Direct contradiction | Patient chart says opposite | Paper says the opposite (or different number) |

### 5-Type Hallucination Taxonomy (simplified from CuraView's 7)

| Type | Meaning | Example |
|---|---|---|
| **wrong_method** | Attributes result to wrong method/architecture | Claim says "BERT" but paper uses "RoBERTa" |
| **wrong_value** | Numeric value differs from paper | Claim says "94.2%" but paper reports "91.7%" |
| **wrong_attribution** | Misattributes finding to wrong source | Claim credits "Smith et al." but paper cites "Jones et al." |
| **missing_context** | Omits important qualifier | Claim drops "on subset X" from the original finding |
| **invented_fact** | Paper does not contain this fact at all | Claim adds a result on a dataset the paper never used |

---

## 2. Domain Mapping: CuraView → CuraVerify

| CuraView (medical discharge) | CuraVerify (scientific abstract) |
|---|---|---|
| MIMIC-IV discharge summary | arXiv / PubMed paper abstract |
| Patient EHR (multi-table) | Full paper PDF (intro / methods / results) |
| Per-patient knowledge graph | Per-paper knowledge graph |
| Entities: diagnosis, medication, lab, procedure, symptom | Entities: **method, dataset, metric, result, claim** |
| Relations: `prescribed_for`, `treated_with`, `measured_by` | Relations: `uses`, `evaluated_on`, `reports`, `improves_over`, `contradicts` |
| Hallucination: wrong dose, fabricated lab | Hallucination: invented result, wrong %, wrong baseline |
| 7 medical types | **5 scientific types** (simplified — see above) |
| E1–E4 evidence grading | Same — unchanged |

The architecture is **adapted** from CuraView. Key simplifications: single verifier agent (CuraView used 3), 5-type taxonomy (CuraView used 7), and no fine-tuning phase (CuraView required medical-domain training data).

---

## 3. Why This Project (Resume / Career ROI)

| Slot | Contribution |
|---|---|
| **LLM engineering depth** | Knowledge graphs, RAG, multi-agent verification, evidence grading — exact skills every AI-engineer JD asks for in 2026 |
| **Domain credibility** | "Built a scientific-paper hallucination detector" puts you in conversation with AI safety / AI-for-science researchers |
| **Public artifact** | GitHub repo with clean README + demo > 5 closed projects on a resume |
| **Local relevance** | Paper-mill crisis in Indian research (India = #2 globally in retractions) — atmanirbhar angle |
| **BBA Viva (Sun Jul 12)** | Working AI system is a strong viva piece — different slot from CoolPulse / Dear Diary |

**Honest downside:** PDF parsing is messy, LLM evals are noisy. The win is pushing through.

---

## 4. Architecture (4-Layer, faithful port of CuraView Fig. 1)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 1 — KNOWLEDGE ACQUISITION (Paper Source Data)                 │
│   Source: arXiv paper.pdf                                           │
│   Extract: title, abstract, sections (intro/methods/results),      │
│            figures/tables captions, references                      │
│   Storage: SQLite papers(id, title, sections_json, full_text)      │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 2 — KNOWLEDGE REPRESENTATION (Per-Paper KG Construction)      │
│   Per paper: NetworkX graph                                         │
│   Node types:  Method, Dataset, Metric, Result, Claim, Section      │
│   Edge types:  uses, evaluated_on, reports,                         │
│                improves_over, contradicts, cited_by                 │
│   Customization (CuraView §6.3.3 inspired):                        │
│     - canonicalize synonyms ("BERT" = "bert-base")                  │
│     - dedup result entities                                         │
│     - normalize metric names ("acc" = "accuracy")                  │
│   Storage: per-paper .gpickle + visualization (HTML)                │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 3 — CLINICAL → SCIENTIFIC EVIDENCE REASONING                  │
│   (GraphRAG + Reasoning Engine)                                     │
│                                                                     │
│   For each abstract sentence:                                       │
│     1. Claim extraction  → atomic claims (one fact each)          │
│     2. Graph retrieval   → 1–2 hop subgraph from claim entities    │
│     3. Evidence path discovery → multi-hop chains                   │
│     4. Relation-aware reasoning → temporal, comparative, negation  │
│     5. Evidence aggregation → evidence package                     │
│                                                                     │
│   Evidence Package = {nodes, relations, chains, source snippets     │
│                       with section+page timestamps}                 │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 4 — VERIFICATION (Single Agent)                               │
│   Verifier (LLM):                                                   │
│     Input:  claim + evidence package                                │
│     Steps:                                                         │
│       1. Evidence grade (E1–E4)                                    │
│       2. Hallucination type (1-of-5, if E3 or E4)                 │
│       3. Citation traceback from evidence package                  │
│       4. Confidence score 0.0–1.0                                  │
│     Built-in consistency checks:                                   │
│       - If grade == E1, type must be null                          │
│       - If claim has a number, citation must contain a number      │
│       - E4 requires confidence ≥ 0.7                               │
│                                                                     │
│   Output: sentence-level verdict + document-level summary           │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Curation

After verification, the system stores (claim, evidence, verdict) triples for error analysis. These are used to identify systematic failure modes and improve prompts — not for fine-tuning.

---

## 5. Implementation Phases

### Phase 0 — Setup (✅ DONE)
- [x] Create `~/CuraVerify/` with subfolders
- [x] Install `pymupdf`, `pymupdf4llm`, `networkx`

### Phase 1 — Data Pipeline (Day 1–4)
- [ ] Pull **50 papers** from arXiv (mix cs.CL / cs.AI / cs.LG)
- [ ] Extract full text with `pymupdf`, preserve section structure (expect ~20% failure rate — log and skip)
- [ ] Build abstract test set:
  - 50 real abstracts (from arXiv metadata)
  - 50 hallucinated abstracts (LLM-rewritten with controlled perturbations — 10 per type across 5 types)
- [ ] **Human annotation**: 2 annotators label 20 abstracts (10 real + 10 hallucinated) for E1–E4 grades. Report Cohen's κ. Use these as ground truth instead of perturbation type.
- [ ] SQLite schema: `papers(id, arxiv_id, title, sections_json, full_text, abstract_real, abstract_test, abstract_is_real)`
- [ ] Validate: spot-check 5 papers, verify section extraction works

### Phase 2 — Knowledge Graph Construction (Day 5–7)
- [ ] Per-paper KG with node types: `Method, Dataset, Metric, Result, Claim, Section`
- [ ] Edge types: `uses, evaluated_on, reports, improves_over, contradicts, cited_by`
- [ ] Entity extraction: LLM call per section → JSON `{entities, relations}`
- [ ] Normalization pass (CuraView §6.3.3 style):
  - Synonym canonicalization (lowercase + alias map)
  - Dedup result entities
  - Numeric normalization (94.2 vs 0.942 → same)
- [ ] Save: 50 `.gpickle` files
- [ ] Visualization: 1 paper rendered as interactive KG (HTML)

### Phase 3 — Verification Engine (Day 8–10)
- [ ] Claim extraction: split abstract into atomic claims (1 fact per claim)
- [ ] Subgraph retrieval: given claim entities → 1–2 hop subgraph
- [ ] Evidence package assembly: nodes + relations + source snippets
- [ ] Verifier prompt: `{claim, evidence_package}` → `{grade, type, citations, reasoning, confidence}`
- [ ] Aggregator: sentence-level → document-level summary
- [ ] Tested end-to-end on 1 paper manually

### Phase 4 — Evaluation & Demo (Day 11–14)
- [ ] Human-annotated ground truth for 20 abstracts ready (from Phase 1)
- [ ] Held-out test set: 10 papers never seen by verifier
- [ ] Metrics: Precision, Recall, F1 on E4 contradiction detection (against human labels, not perturbation types)
- [ ] Report Cohen's κ between annotators and between verifier vs. humans
- [ ] Baseline comparison: flat retrieval (RAGTruth-style) vs. GraphRAG (us)
- [ ] Hypothesis: GraphRAG wins on **precision** (matches CuraView's claim)
- [ ] Streamlit / Gradio demo: upload PDF + abstract → live verdict with evidence tracebacks
- [ ] Demo video: 3 minutes, screen-recorded

### Phase 5 — Stretch (if time)
- [ ] Cross-domain test: 5 papers from biology / finance / policy
- [ ] Qualitative error analysis: categorize 20+ failure cases from the eval
- [ ] arXiv / SSRN preprint draft:
  > *"CuraVerify: A Domain-Port of CuraView to Scientific Literature Faithfulness Verification"*
- [ ] GitHub repo: README + architecture diagram + results table + demo gif

---

## 6. Tech Stack

| Layer | Tool | Status |
|---|---|---|
| PDF parsing | `pymupdf` + `pymupdf4llm` | ✅ installed |
| KG | `networkx` | ✅ installed |
| Storage | SQLite + JSON | ✅ stdlib |
| LLM | `minimax-M3` (default), or `claude-sonnet-4` via API for higher quality | available |
| arXiv fetch | REST API via stdlib | ✅ no deps |
| UI | Streamlit | to install in Phase 4 |
| Repo | GitHub | pending |
| Eval | scikit-learn metrics | to install in Phase 4 |
| Visualization | pyvis (KG HTML) | to install in Phase 2 |

**Zero new installs needed beyond `pymupdf` and `networkx` to start Phases 1–3.**

---

## 7. File / Folder Structure

```
CuraVerify/
├── PROJECT_PLAN.md            ← this file
├── ARCHITECTURE.md            ← deep dive on 4-layer architecture
├── DATA_SCHEMA.md             ← SQLite schema + KG schema
├── PROMPTS.md                 ← all LLM prompts used
├── EVAL_PLAN.md               ← evaluation methodology
├── README.md                  ← public-facing, for GitHub
│
├── data/
│   ├── papers_metadata.json   ← arXiv metadata (50 papers)
│   ├── raw_pdfs/              ← downloaded PDFs
│   ├── processed/             ← extracted text + sections JSON
│   ├── abstracts/             ← real + hallucinated abstract sets
│   └── knowledge_graphs/      ← per-paper .gpickle files
│
├── src/
│   ├── __init__.py
│   ├── fetch_arxiv.py         ← Phase 1: pull papers
│   ├── extract_pdf.py         ← Phase 1: PDF → sections
│   ├── build_abstracts.py     ← Phase 1: real + hallucinated abstracts
│   ├── build_kg.py            ← Phase 2: KG construction
│   ├── extract_entities.py    ← Phase 2: LLM entity extraction
│   ├── normalize_kg.py        ← Phase 2: synonym canonicalization
│   ├── verify.py              ← Phase 3: claim extraction + verification
│   ├── evidence_package.py    ← Phase 3: subgraph retrieval
│   ├── verifier_prompts.py    ← Phase 3: prompts
│   ├── aggregate.py           ← Phase 3: sentence→document
│   ├── evaluate.py            ← Phase 4: metrics
│   └── baseline_flat.py       ← Phase 4: flat-retrieval baseline
│
├── prompts/
│   ├── entity_extraction.txt
│   ├── claim_extraction.txt
│   ├── verification.txt
│   └── hallucination_type.txt
│
├── results/
│   ├── eval_table.md
│   ├── confusion_matrix.png
│   └── type_wise_f1.csv
│
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_kg_visualization.ipynb
│   └── 03_demo_walkthrough.ipynb
│
└── tests/
    ├── test_extract_pdf.py
    ├── test_build_kg.py
    └── test_verify.py
```

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| arXiv PDF parsing fails on some papers (multi-column, math) | Use `pymupdf4llm` markdown mode; fallback to text; log failures |
| LLM gives noisy entity extraction | Schema validation + retry + JSON repair; spot-check 5 papers |
| GraphRAG doesn't beat baseline on our 50-paper scale | This is honest research — negative result still publishable; report it cleanly |
| Hallucinated abstracts look too "obviously" wrong | Use controlled perturbations (mirroring 5-type taxonomy) with subtle deltas |
| MIMIC-IV doesn't release code (no reply from authors) | Doesn't affect us — we built from architecture description, independently |

---

## 9. Success Criteria

**Minimum (resume-worthy):**
- 50 papers processed end-to-end
- Working verifier demo on Streamlit
- README + clean GitHub repo
- One ablation: GraphRAG vs. flat-retrieval on E4 F1

**Strong (paper-worthy):**
- 100+ papers across 2+ domains
- Held-out evaluation with baseline comparison and human annotation
- Qualitative error taxonomy from 20+ failure cases
- Preprint on arXiv / SSRN

**Stretch:**
- Domain-port to a 3rd domain (legal / financial)
- Real user study with researchers

---

## 10. Timeline

| Phase | Days | Deliverable |
|---|---|---|---|
| 0 | 0 | Project folder ✅ |
| 1 | 1–4 | 50 papers + abstract test set + human annotation |
| 2 | 5–7 | 50 KGs + 1 visualization |
| 3 | 8–10 | Working verifier end-to-end |
| 4 | 11–14 | Eval + demo + repo |
| 5 | 15–18 | Cross-domain + error analysis + preprint |

**BBA Viva target: Sun Jul 12** — Phase 4 minimum is doable by then.

---

## 11. References

- **CuraView paper:** Ye, S. et al. (2025). *CuraView: A Knowledge-Based Multi-Agent Framework for Patient-Grounded Medical Hallucination Detection with GraphRAG-Enhanced Evidence Verification.* SSRN 7065322. https://ssrn.com/abstract=7065322
- **GraphRAG:** Edge, D. et al. (2024). *From Local to Global: A Graph RAG Approach to Query-Focused Summarization.* arXiv:2404.16130
- **Discharge-Me:** Xu, J. et al. (2024). *Overview of the First Shared Task on Clinical Text Generation: RRG24 and "Discharge Me!"* BioNLP Workshop.
- **RAGTruth / QAGS:** Reference hallucination detection baselines.