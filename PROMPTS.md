# CuraVerify — LLM Prompts

> All prompts used in the 4-layer pipeline. Edit and version these as we learn what works.

---

## Prompt 1: Entity Extraction (Layer 2)

**Purpose:** Extract structured entities + relations from a paper section.

**Usage:** Called per section of paper (intro, methods, results, etc.)

```
You are extracting structured scientific information from a paper section.

SECTION: {section_name}

SECTION TEXT:
\"\"\"
{section_text}
\"\"\"

TASK: Extract all scientific entities and relations as JSON.

ENTITY TYPES:
- method: ML methods, models, architectures (e.g., "BERT", "GPT-4", "LoRA")
- dataset: benchmarks, datasets, corpora (e.g., "GLUE", "SQuAD", "ImageNet")
- metric: evaluation metrics (e.g., "accuracy", "F1", "BLEU")
- result: specific numeric findings (e.g., "94.2% accuracy on GLUE")

RELATION TYPES:
- uses: (method) → (dataset) or (method) → (method)
- evaluated_on: (result) → (dataset)
- reports: (result) → (metric)
- improves_over: (result) → (result)

OUTPUT (JSON only, no commentary):
{
  "entities": [
    {"type": "method|dataset|metric|result", "name": "...", "aliases": [...], "context_snippet": "..."},
    ...
  ],
  "relations": [
    {"source": "<entity_name>", "target": "<entity_name>", "type": "uses|evaluated_on|reports|improves_over", "evidence": "..."},
    ...
  ]
}

CONSTRAINTS:
- Only extract facts EXPLICITLY stated in the text. Do NOT infer.
- For "result" entities, capture the exact numeric value and unit.
- Use canonical names (lowercase, no punctuation). Aliases capture variants.
- If a section is short or contains no extractable entities, return empty arrays.
```

---

## Prompt 2: Claim Extraction (Layer 3.1)

**Purpose:** Split an abstract sentence into atomic claims.

```
You are extracting atomic factual claims from a sentence.

SENTENCE: "{sentence_text}"

TASK: Decompose the sentence into the smallest set of atomic claims.
Each claim expresses exactly ONE fact (subject + predicate + object).

OUTPUT (JSON only):
[
  {
    "claim_text": "...",
    "subject": "...",
    "predicate": "achieves|outperforms|uses|reports|introduces|...",
    "object": "...",
    "dataset": "..." (if applicable),
    "metric": "..." (if applicable),
    "value": ... (if numeric)
  },
  ...
]

RULES:
- "BERT achieves 94.2% accuracy on GLUE" → 1 atomic claim (subject=BERT, predicate=achieves, object=94.2%, dataset=GLUE, metric=accuracy)
- "BERT outperforms RoBERTa by 2.3 points on GLUE" → 1 atomic comparative claim (subject=BERT, predicate=outperforms, object=RoBERTa, dataset=GLUE, value=2.3)
- "We propose X, achieving Y on Z" → 1 atomic claim about Y (the contribution is implicit)
- If a sentence is purely rhetorical or has no verifiable fact, return empty array.
```

---

## Prompt 3: Claim Verification (Layer 4 — Agent A)

**Purpose:** Verify a claim against evidence package, return E1–E4 grade + type.

```
You are a scientific-paper hallucination verifier.

CLAIM:
{claim_text}

EVIDENCE PACKAGE (from the source paper's knowledge graph):
{evidence_package_json}

TASK:
1. Determine EVIDENCE GRADE:
   - E1 (Strong support): The paper explicitly states this claim with matching specifics.
   - E2 (Weak support): The paper supports a paraphrase or rounded version (e.g., 94% vs 94.2%).
   - E3 (No support): The paper does not contain evidence for this claim.
   - E4 (Direct contradiction): The paper explicitly states a different value or the opposite.

2. If grade is E3 or E4, classify HALLUCINATION TYPE:
   - wrong_method: attributes result to wrong method
   - wrong_value: numeric value differs from paper
   - wrong_attribution: misattributes finding to wrong source
   - missing_context: omits important qualifiers (e.g., subset, time period)
   - invented_fact: paper does not contain this fact at all

3. Cite supporting evidence (sections + snippets from the evidence package).
4. Provide one-sentence reasoning.
5. Estimate confidence 0.0-1.0.

OUTPUT (JSON only):
{
  "grade": "E1|E2|E3|E4",
  "hallucination_type": "wrong_method|wrong_value|wrong_attribution|missing_context|invented_fact" or null,
  "citations": [
    {"section": "...", "paragraph_id": ..., "snippet": "..."}
  ],
  "reasoning": "...",
  "confidence": 0.0
}

RULES:
- Be conservative: if evidence is partial or ambiguous, prefer E2 over E1.
- For numeric mismatches: small differences (< 5%) → E2; large differences → E4.
- If evidence package is empty or irrelevant, grade is E3 (no support).
- Confidence should reflect your certainty in the grade assignment.
```

---

## Prompt 4: Abstract Hallucination Generation (Phase 1 — Training Data)

**Purpose:** Generate realistic hallucinated abstracts for training/testing.

```
You are generating a realistic hallucinated scientific-paper abstract.

ORIGINAL ABSTRACT:
\"\"\"
{original_abstract}
\"\"\"

PAPER TITLE: {title}
PAPER ARXIV ID: {arxiv_id}

TASK: Rewrite the abstract with EXACTLY ONE hallucination of the specified type.
The rewrite should be plausible — a careless reader might miss the error.

HALLUCINATION TYPE: {perturbation_type}

GUIDE PER TYPE:
- wrong_method: replace one method/architecture name with a different (real) method
- wrong_value: change one numeric result by 5-20%
- wrong_attribution: change which paper/source is being credited
- missing_context: remove a qualifier (e.g., "on subset X" → drop "on subset X")
- invented_fact: add a claim that goes BEYOND what the paper shows (e.g., add a result on a dataset the paper doesn't use)

CONSTRAINTS:
- Keep the abstract's overall structure and length similar.
- Make the change SUBTLE — only one factual error.
- The rest of the abstract must still be faithful to the paper.

OUTPUT (JSON only):
{
  "rewritten_abstract": "...",
  "modified_sentence_idx": ...,  # 0-based index of the sentence containing the hallucination
  "explanation": "What was changed and why it's a hallucination."
}
```

---

## Prompt 5: Document-Level Verdict (Layer 4 — Aggregator)

**Purpose:** Aggregate sentence-level verdicts into a document-level summary.

```
You are aggregating sentence-level hallucination verdicts into a document-level assessment.

SENTENCE-LEVEL VERDICTS:
{verdicts_json}

TASK: Provide a one-paragraph overall assessment.

OUTPUT (JSON only):
{
  "overall_verdict": "OK|SUSPICIOUS|LIKELY_HALLUCINATED|CONTAINS_CRITICAL_ERRORS",
  "summary": "...",
  "key_concerns": ["...", "..."],
  "recommendation": "Accept as-is | Review specific sentences | Reject"
}
```

---

## Prompt Configuration

```yaml
# prompts/config.yaml
prompts:
  entity_extraction:
    model: minimax-M3
    temperature: 0.0
    max_tokens: 2000
    json_mode: true

  claim_extraction:
    model: minimax-M3
    temperature: 0.0
    max_tokens: 500
    json_mode: true

  claim_verification:
    model: minimax-M3
    temperature: 0.0
    max_tokens: 1000
    json_mode: true

  hallucination_generation:
    model: minimax-M3
    temperature: 0.7
    max_tokens: 1500
    json_mode: true

  document_verdict:
    model: minimax-M3
    temperature: 0.0
    max_tokens: 500
    json_mode: true
```

---

## Versioning

| Version | Date | Notes |
|---|---|---|
| 0.2.0 | 2026-07-12 | Simplified: removed Agent B refiner, 5-type taxonomy, single verifier |