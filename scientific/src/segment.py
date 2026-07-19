"""Stage 2 — sentence segmentation + light atomic-claim extraction."""
from __future__ import annotations

import re
from typing import List

_ABBREV = re.compile(
    r"\b(?:e\.g|i\.e|vs|Dr|Mr|Mrs|Ms|Prof|Fig|Eq|al|etc)\.",
    re.IGNORECASE,
)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])")


def split_sentences(text: str) -> List[str]:
    if not text or not text.strip():
        return []
    # Protect common abbreviations from splitting.
    masked = _ABBREV.sub(lambda m: m.group(0).replace(".", "<DOT>"), text.strip())
    parts = _SENT_SPLIT.split(masked)
    out = []
    for p in parts:
        s = p.replace("<DOT>", ".").strip()
        if len(s) >= 15:
            out.append(s)
    return out or [text.strip()]


def atomic_claims(sentence: str) -> List[dict]:
    """Heuristic: treat each sentence as one claim; attach numbers if present."""
    nums = re.findall(r"\d+(?:\.\d+)?%?", sentence)
    return [
        {
            "claim_text": sentence,
            "subject": sentence.split()[0] if sentence.split() else "",
            "predicate": "states",
            "object": nums[0] if nums else "",
            "values": nums,
        }
    ]
