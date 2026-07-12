# CuraVerify — Evaluation Plan

> How we measure whether the verifier works, mirroring CuraView's evaluation methodology.

---

## 1. Goals

We want to measure three things, in order of importance:

1. **Safety-critical detection (E4):** Can we catch direct contradictions?
2. **General hallucination detection (E3+E4):** Can we catch unsupported AND contradictory claims?
3. **Fine-grained type classification:** Which hallucination types do we handle well?

---

## 2. Test Data

### Source: 50 arXiv papers (cs.CL, cs.AI, cs.LG)

For each paper:
- 1 real abstract (from arXiv metadata)
- 1 hallucinated abstract per perturbation type (5 types) — 10 per type

### Train / Test Split

| Split | Papers | Use |
|---|---|---|
| **Train** | 40 papers | Develop prompts, tune thresholds, identify failure modes |
| **Test (held-out)** | 10 papers | Final evaluation, never seen during development |

Test set is **never used for prompt engineering** — only for final reporting.

### Annotation

**Critical — ground truth is NOT determined by perturbation type alone.** Real abstracts can contain E2–E4 claims (authors oversell). Hallucinated abstracts may accidentally be faithful. Using perturbation type as ground truth biases metrics upward.

Instead:
- **2 human annotators** independently label each sentence in 20 abstracts (10 real + 10 hallucinated) as E1–E4
- Report **Cohen's κ** for inter-annotator agreement
- Where annotators disagree, a third annotator adjudicates
- These human-labeled grades are the **ground truth** for eval
- The remaining 30 papers use perturbation type as a weak label (with this caveat documented)

---

## 3. Primary Metrics

### Per-Grade F1 (matching CuraView Table 4)

For each evidence grade (E1, E2, E3, E4):
- **Precision:** Of sentences we labeled grade X, how many are truly grade X?
- **Recall:** Of sentences truly grade X, how many did we label correctly?
- **F1:** Harmonic mean

**Primary metric: E4 F1** (safety-critical, most important)

### Hallucination Detection (E3+E4)

- **Precision:** Of sentences we flagged (E3 or E4), how many are truly hallucinated?
- **Recall:** Of truly hallucinated sentences, how many did we flag?
- **F1:** Harmonic mean

### Type-Wise F1

For each of the 5 hallucination types:
- **Type-wise F1** on the test set
- Report per-type precision and recall to identify which types are hardest

Note: fine-tuning is out of scope (not enough data). Type-wise F1 measures the verifier's inherent classification accuracy per type.

---

## 4. Baselines

We compare CuraVerify against two flat-retrieval baselines (matching CuraView's comparison):

### Baseline 1: RAGTruth-style
- Split paper into passages (1 paragraph each)
- For each abstract sentence, retrieve top-k passages via embedding similarity
- LLM verifies sentence against retrieved passages only (no KG, no relations)
- Same E1–E4 grading scheme

### Baseline 2: QAGS-style
- Similar to RAGTruth but uses QA-style answer generation + comparison
- Sentence → questions → answers → compare to abstract

### Why Baselines Matter

CuraView showed GraphRAG wins primarily on **precision** (not recall).
Flat retrieval has high recall (finds suspicious sentences) but low precision (many false positives).
GraphRAG reduces false positives by structuring evidence.

We expect the same pattern on scientific papers.

---

## 5. Evaluation Pipeline

```python
# Pseudocode
def evaluate(test_papers, verifier, baselines):
    results = {method: [] for method in ['curavverify', 'ragtruth', 'qags']}

    for paper in test_papers:
        for abstract in [paper.real_abstract, paper.hallucinated_abstract]:
            for method_name, method_fn in [('curavverify', verifier), ...]:
                verdicts = method_fn(paper, abstract)
                results[method_name].append({
                    'paper_id': paper.id,
                    'sentences': verdicts,
                    'ground_truth': abstract.ground_truth_grades
                })

    # Compute metrics per method
    for method_name, results_list in results.items():
        metrics[method_name] = compute_metrics(results_list)

    return metrics
```

---

## 6. Confusion Matrix

Per evidence grade (E1–E4), build a 4×4 confusion matrix:

```
             Predicted
             E1   E2   E3   E4
True  E1  [ ] [ ] [ ] [ ]
      E2  [ ] [ ] [ ] [ ]
      E3  [ ] [ ] [ ] [ ]
      E4  [ ] [ ] [ ] [ ]
```

Saved to `results/confusion_matrix.png`.

---

## 7. Type-Wise Analysis

For each hallucination type, report:

| Type | Test samples | Precision | Recall | F1 |
|---|---|---|---|---|
| wrong_value | N | X | Y | Z |
| invented_fact | N | X | Y | Z |
| wrong_method | N | X | Y | Z |
| wrong_attribution | N | X | Y | Z |
| missing_context | N | X | Y | Z |

This identifies which types the verifier handles well and which need prompt improvements.

---

## 8. Qualitative Analysis (CuraView §6.5 style)

### 2 representative cases (1 success, 1 failure):

**Case 1 — Successful E4 detection:**
- Original sentence: "BERT achieves 94.2% accuracy on GLUE"
- Rewritten (wrong_value): "BERT achieves 96.8% accuracy on GLUE"
- Our verdict: E4 with correct type "wrong_value" and correct citation
- Why it worked: paper explicitly states 91.7%; mismatch is clear

**Case 2 — False positive:**
- Original sentence: "Our model achieves 91.7% accuracy on GLUE"  (faithful)
- Our verdict: E3 ("not supported")
- Why it failed: paper says 91.7% in Section 4.2 but our retrieval missed it; or synonym mismatch ("BERT-base" vs "our model")

These cases go in the README and any future paper.

---

## 9. Ablation Studies (CuraView §6.3 inspired)

### Ablation 1: KG vs. no KG
- **Full system:** GraphRAG + verification
- **Ablated:** Flat retrieval + verification
- Hypothesis: KG helps precision, hurts recall slightly

### Ablation 2: Domain-customized KG vs. raw KG
- **Full system:** Customized (synonym canonicalization, dedup, metric aliasing)
- **Ablated:** Raw KG without customization
- Hypothesis: customization helps F1

### Ablation 3: With vs. without relation-aware reasoning
- **Full system:** Uses evidence chains + relation types from KG
- **Ablated:** Flat retrieved text chunks (no relation labels, no path structure)
- Hypothesis: relation-aware reasoning helps for comparative claims ("outperforms by X")

---

## 10. Generalization Test (CuraView §6.4 inspired)

### Meditron case study analog: cross-domain test

Run the verifier on 5 papers from a domain **not in training** (e.g., biomedical NLP, finance):
- Compare hallucination rate
- Compare type distribution
- Report whether the system generalizes or breaks

Expected: invented-fact rate will be high in real-world generated text, just like CuraView's 84.4% finding.

---

## 11. Reporting

### Results Table (`results/eval_table.md`)

```markdown
| Method | E4 F1 | E3+E4 F1 | E4 Precision | E4 Recall | E3 Precision | E3 Recall |
|---|---|---|---|---|---|---|
| CuraVerify (ours) | 0.XX | 0.XX | 0.XX | 0.XX | 0.XX | 0.XX |
| RAGTruth-style baseline | 0.XX | 0.XX | 0.XX | 0.XX | 0.XX | 0.XX |
| QAGS-style baseline | 0.XX | 0.XX | 0.XX | 0.XX | 0.XX | 0.XX |
```

### Type-Wise Table (`results/type_wise_f1.csv`)

CSV with columns: `type, train_samples, base_f1, curavverify_f1, ceiling_gain`

### Figures

- `results/confusion_matrix.png` — 4×4 confusion matrix for E1–E4
- `results/type_wise_gain.png` — bar chart matching CuraView Figure 7
- `results/kg_visualization.html` — interactive KG for one paper

---

## 12. Success Criteria (revised)

**Minimum (resume-worthy):**
- ✅ E4 F1 > 0.50 (better than random)
- ✅ Demonstrates GraphRAG > flat retrieval on precision (matches CuraView's finding)
- ✅ Working Streamlit demo
- ✅ Public GitHub repo

**Strong (paper-worthy):**
- ✅ E4 F1 > 0.70 (competitive with CuraView's 0.831)
- ✅ Type-wise F1 reported for all 5 types
- ✅ Human annotation agreement (Cohen's κ > 0.70)
- ✅ Cross-domain generalization test
- ✅ arXiv preprint draft

**Stretch:**
- ✅ E4 F1 > 0.80 (matches CuraView)
- ✅ Qualitative error taxonomy published
- ✅ User study with researchers

---

## 13. Timeline for Evaluation Phase

| Day | Activity |
|---|---|
| 11 | Build eval pipeline (`src/evaluate.py`), run on 5 dev papers |
| 12 | Run on human-annotated 20-abstract ground truth set |
| 13 | Implement baselines, run comparison, generate tables/figures |
| 14 | Write up results section, prepare demo |
| 15+ | Stretch: cross-domain, error analysis, preprint |