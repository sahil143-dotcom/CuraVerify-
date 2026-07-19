# BioLaySumm → CuraVerify Download Summary

## What the website offers

| Track | Datasets | Essential for CuraVerify? |
|---|---|---|
| Task 1 Lay summarization | PLOS, eLife (article ↔ lay summary) | **YES** |
| Task 2 Radiology lay terms | PadChest, BIMCV, Open-i, MIMIC-CXR | No (images / RRG) |

**Downloaded strategy:** full eLife + PLOS val/test + PLOS train sample

Output: `D:\CuraVerify\scientific\data\biolaysumm`

## eLife

| Split | Rows | Median article chars | Median summary chars |
|---|---:|---:|---:|
| train | 4346 | 55748 | 2191 |
| validation | 241 | 54612 | 2247 |
| test | 142 | 45940 | 0 |

## PLOS

| Split | Rows | Median article chars | Median summary chars |
|---|---:|---:|---:|
| validation | 1376 | 37933 | 1260 |
| test | 142 | 43483 | 0 |
| train_sample | 800 | 38216 | 1272 |

## Schema (both datasets)

| Field | CuraVerify role |
|---|---|
| `article` | Source document (ground truth) |
| `summary` | Lay summary to verify |
| `section_headings` | Structure for evidence retrieval |
| `title`, `keywords`, `year` | Metadata |

## Important note on TEST splits

Official **test** summaries are **blank** (shared-task blind eval).  
For CuraVerify, use **train + validation** only (they have gold lay summaries).

Usable for faithfulness work right now:
- eLife train+val = **4,587** pairs with summaries
- PLOS train_sample+val = **2,176** pairs with summaries
- **Total usable ≈ 6,763** article↔summary pairs

## Next step for CuraVerify

1. Split each `summary` into atomic claims
2. Retrieve evidence snippets from `article`
3. Grade E1–E4 (support / weak / none / contradict)
4. Optionally inject controlled hallucinations into summaries for eval

Preview samples: `D:\CuraVerify\scientific\data\biolaysumm\preview_samples.json`
