# CuraVerify — Scientific Arm (BioLaySumm)

Complete product port of **CuraView** (SSRN 7065322) six-stage hallucination detection onto **BioLaySumm** article ↔ lay-summary pairs.

## CuraView 6 stages → this code

| Stage | Meaning | Module |
|---|---|---|
| 1 Input | Article + lay summary | `load_biolaysumm.py` → SQLite |
| 2 Segment | Sentences / claims | `segment.py` |
| 3 Evidence | GraphRAG package | `build_kg.py` + `evidence_package.py` |
| 4 Judge | Hybrid verifier | `verify.py` |
| 5 Grade | E1–E4 + 5 types | `verify.py` + `models.py` |
| 6 Emit | Schema + QC + doc verdict | `models.py` + `aggregate.py` |

Plus data curation (`hallucinate.py`) and eval (`evaluate.py` vs flat baseline).

## Quickstart

```powershell
# from repo root D:\CuraVerify
# Prefer a venv on D: if C: is low on space
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scientific\requirements.txt

# Lean UI (bundled demo samples)
.\.venv\Scripts\streamlit.exe run scientific\app.py

# Full pipeline: load → KG → hallucinate → verify → metrics
.\.venv\Scripts\python.exe -m scientific.run_pipeline
```

Latest local run (example): **6,763** papers loaded, **200** KGs, **50** hallucinated summaries, E3+E4 F1 ≈ **0.71** (see `results/eval_table.md`).

Deploy to Hugging Face Spaces: see [DEPLOY.md](DEPLOY.md).

Optional LLM refinement (otherwise offline hybrid rules):

```bash
set CURAVERIFY_LLM_API_KEY=sk-...
set CURAVERIFY_LLM_MODEL=gpt-4o-mini
```

## Layout

```
scientific/
├── run_pipeline.py          # orchestrator
├── app.py                   # Streamlit demo
├── requirements.txt
├── data/
│   ├── biolaysumm/          # JSONL source
│   ├── scientific.db        # SQLite
│   └── knowledge_graphs/    # *.gpickle
├── results/
│   ├── eval_table.md
│   ├── eval_metrics.json
│   └── eval_metrics.csv
└── src/
    ├── load_biolaysumm.py
    ├── segment.py
    ├── extract_entities.py
    ├── build_kg.py
    ├── evidence_package.py
    ├── verify.py
    ├── models.py
    ├── aggregate.py
    ├── hallucinate.py
    ├── baseline_flat.py
    └── evaluate.py
```

## Evidence grades

| Grade | Meaning |
|---|---|
| E1 | Strong support |
| E2 | Weak / paraphrase support |
| E3 | No support |
| E4 | Contradiction |

Hallucination types (if E3/E4): `wrong_method`, `wrong_value`, `wrong_attribution`, `missing_context`, `invented_fact`.
