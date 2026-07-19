"""Aggregate sentence-level verdicts into a document-level summary."""
from __future__ import annotations

from typing import List

from .models import ClaimVerdict, DocumentVerdict


def aggregate_verdicts(summary_id: int, verdicts: List[ClaimVerdict], method: str = "graphrag") -> DocumentVerdict:
    counts = {"E1": 0, "E2": 0, "E3": 0, "E4": 0}
    for v in verdicts:
        counts[v.grade] = counts.get(v.grade, 0) + 1
    total = max(len(verdicts), 1)
    hall_rate = (counts["E3"] + counts["E4"]) / total
    contra_rate = counts["E4"] / total

    if counts["E4"] >= 1 and hall_rate >= 0.3:
        overall = "CONTAINS_CRITICAL_ERRORS"
    elif counts["E4"] >= 1 or hall_rate >= 0.35:
        overall = "LIKELY_HALLUCINATED"
    elif hall_rate >= 0.15:
        overall = "SUSPICIOUS"
    else:
        overall = "OK"

    return DocumentVerdict(
        summary_id=summary_id,
        total_sentences=len(verdicts),
        count_e1=counts["E1"],
        count_e2=counts["E2"],
        count_e3=counts["E3"],
        count_e4=counts["E4"],
        hallucination_rate=round(hall_rate, 4),
        contradiction_rate=round(contra_rate, 4),
        overall_verdict=overall,  # type: ignore[arg-type]
        method=method,
    )


def document_verdict_to_db_row(dv: DocumentVerdict) -> dict:
    return dv.model_dump()
