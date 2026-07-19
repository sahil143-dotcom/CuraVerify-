"""Pydantic models for Stage 6 structured emission + QC."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

Grade = Literal["E1", "E2", "E3", "E4"]
HallucinationType = Optional[
    Literal[
        "wrong_method",
        "wrong_value",
        "wrong_attribution",
        "missing_context",
        "invented_fact",
    ]
]


class Citation(BaseModel):
    section: str = "article"
    paragraph_id: int = 0
    snippet: str = ""


class ClaimVerdict(BaseModel):
    sentence_idx: int
    sentence_text: str
    grade: Grade
    hallucination_type: HallucinationType = None
    citations: List[Citation] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    claims: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_package: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def clip_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    @model_validator(mode="after")
    def consistency_gates(self) -> "ClaimVerdict":
        # E1 ⇒ type must be null
        if self.grade == "E1":
            self.hallucination_type = None
        # E3/E4 require a type
        if self.grade in ("E3", "E4") and not self.hallucination_type:
            self.hallucination_type = "invented_fact"
        # E4 requires confidence >= 0.7
        if self.grade == "E4" and self.confidence < 0.7:
            self.confidence = 0.7
        # E2 should not carry a hard hallucination type
        if self.grade == "E2":
            self.hallucination_type = None
        return self


class DocumentVerdict(BaseModel):
    summary_id: int
    total_sentences: int
    count_e1: int
    count_e2: int
    count_e3: int
    count_e4: int
    hallucination_rate: float
    contradiction_rate: float
    overall_verdict: Literal[
        "OK", "SUSPICIOUS", "LIKELY_HALLUCINATED", "CONTAINS_CRITICAL_ERRORS"
    ]
    method: str = "graphrag"
