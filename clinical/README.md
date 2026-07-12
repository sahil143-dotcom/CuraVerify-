# CuraVerify — Clinical Arm

The **clinical-domain sibling** of CuraVerify. Same 4-layer architecture
(acquire → KG → evidence → verify), but applied to **clinical text** instead of
scientific papers. Built on the open **MTSamples** dataset (~5k real transcribed
medical reports — no credentialing, no PHI risk), so it runs anywhere.

This turns CuraVerify into a **two-domain system** (scientific + clinical),
which is exactly the cross-domain goal in `../EVAL_PLAN.md` §10.

## Roadmap

| Day | Focus | NLP you learn | Status |
|---|---|---|---|
| **1** | Data + EDA | text cleaning, sectioning, dataset profiling | ✅ built |
| 2 | Clinical NER | NER, negation, UMLS entity linking (scispaCy/medspaCy) | next |
| 3 | KG + verifier | relation extraction, evidence grounding (E1–E4) | planned |
| 4 | Demo + writeup | Streamlit app, README | planned |

## Day 1 — what it does

1. **Acquire** MTSamples into `data/raw/mtsamples.csv` (`kagglehub` → raw mirrors → manual fallback).
2. **Clean + section** each note (whitespace normalize, dedupe, split on ALL-CAPS headers).
3. **Store** into SQLite `data/clinical.db` (`clinical_notes` table).
4. **EDA**: specialty mix, note lengths, section-header frequency → figures + `results/eda_report.md`.

## Setup

```bash
# from the repo root:  D:\CuraVerify
python -m pip install -r clinical/requirements.txt
```

## Run Day 1

One command (acquire → load → EDA):

```bash
python -m clinical.run_day1
```

Or step by step:

```bash
python -m clinical.src.download_data      # fetch mtsamples.csv
python -m clinical.src.load_mtsamples     # clean + load into clinical.db
python -m clinical.src.eda                # figures + report
```

Interactive version:

```bash
jupyter notebook clinical/notebooks/clinical_01_eda.ipynb
```

## Layout

```
clinical/
├── README.md
├── requirements.txt
├── run_day1.py                 # Day 1 orchestrator
├── src/
│   ├── config.py               # paths, dataset URLs, constants
│   ├── download_data.py        # resilient MTSamples acquisition
│   ├── sectioner.py            # ALL-CAPS header section splitter (reused Day 2+)
│   ├── load_mtsamples.py       # clean + section + load -> SQLite
│   ├── db.py                   # clinical_notes schema + helpers
│   └── eda.py                  # headless EDA (figures + report)
├── notebooks/
│   └── clinical_01_eda.ipynb   # interactive EDA
├── data/                       # (gitignored) raw csv + clinical.db
└── results/                    # (gitignored) EDA figures + report
```

## `clinical_notes` schema

| column | meaning |
|---|---|
| `sample_name` | e.g. "Cardiology Consult - 1" |
| `description` | one-line description |
| `medical_specialty` | normalized specialty label |
| `keywords` | comma-separated keywords |
| `transcription` | cleaned full note text |
| `char_count` / `word_count` | length metrics |
| `section_count` | number of detected sections |
| `sections_json` | JSON `{header: body}` |

## Data note

MTSamples are publicly shared, already-de-identified sample transcriptions —
safe to use and commit *code* against, but the raw CSV and DB are gitignored by
default. For real EHR text (MIMIC-IV, n2c2), obtain PhysioNet credentialing;
the same pipeline will accept it with a new loader.
