"""Flat-retrieval baseline (RAGTruth-style): no KG, paragraph overlap only."""
from __future__ import annotations

from typing import List

from .models import ClaimVerdict
from .verify import verify_summary_against_article


def verify_flat(
    summary_text: str,
    article: str,
    paper_id: int = 0,
    title: str = "",
) -> List[ClaimVerdict]:
    return verify_summary_against_article(
        summary_text=summary_text,
        article=article,
        paper_id=paper_id,
        title=title,
        method="flat",
    )
