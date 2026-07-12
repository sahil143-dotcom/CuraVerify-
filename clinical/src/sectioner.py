"""Section detection for MTSamples clinical notes.

Clinical transcriptions use ALL-CAPS headers followed by a colon, e.g.::

    CHIEF COMPLAINT:, HISTORY OF PRESENT ILLNESS:, PAST MEDICAL HISTORY:,
    MEDICATIONS:, ALLERGIES:, PHYSICAL EXAMINATION:, ASSESSMENT:, PLAN:

Headers frequently appear inline (not only at line starts), so we scan the
whole string for uppercase header patterns and slice between them.

This module is intentionally dependency-free (stdlib `re` only) because
Day 2's NER pipeline reuses it to attach entities to their source section.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

# An uppercase header: starts with a capital letter, is made of uppercase
# word-characters joined by spaces / a few punctuation marks, and ends in a colon.
# Requires at least 3 characters so we don't match stray initials like "T:".
_HEADER_RE = re.compile(
    r"""
    (?:^|(?<=[\s.]))                       # start-of-string, or after whitespace/period
    (?P<header>
        [A-Z][A-Z0-9]{0,}                  # first uppercase word
        (?:[ /&,'()\-]+[A-Z0-9][A-Z0-9]*)* # optional following uppercase words
    )
    \s*:                                    # the colon that terminates a header
    """,
    re.VERBOSE,
)

# Headers must be at least this long (letters only) to count. Filters out noise
# like "MR:" while keeping real short headers such as "CC" (chief complaint).
_MIN_HEADER_LETTERS = 2

# Common real headers that are short — always allowed even if < min length rule.
_KNOWN_SHORT_HEADERS = {"CC", "HPI", "PMH", "PSH", "ROS", "FH", "SH", "PE", "A", "P"}


def _is_plausible_header(header: str) -> bool:
    letters = re.sub(r"[^A-Z]", "", header)
    if header in _KNOWN_SHORT_HEADERS:
        return True
    if len(letters) < _MIN_HEADER_LETTERS:
        return False
    # Reject pure numbers / single stray letters already handled above.
    return True


def find_headers(text: str) -> List[Tuple[int, int, str]]:
    """Return a list of (start, end, header_text) for each detected header.

    `start`/`end` bound the header token itself (excluding the colon body).
    """
    spans: List[Tuple[int, int, str]] = []
    for m in _HEADER_RE.finditer(text):
        header = m.group("header").strip()
        if _is_plausible_header(header):
            spans.append((m.start("header"), m.end(), header))
    return spans


def split_sections(text: str) -> Dict[str, str]:
    """Split a clinical note into {header: body} using detected headers.

    If no headers are found, returns {"UNSECTIONED": <whole text>}.
    Duplicate headers are disambiguated with a numeric suffix.
    """
    if not text or not text.strip():
        return {}

    headers = find_headers(text)
    if not headers:
        return {"UNSECTIONED": text.strip()}

    sections: Dict[str, str] = {}
    for i, (h_start, h_end, header) in enumerate(headers):
        body_start = h_end
        body_end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
        body = text[body_start:body_end].strip()

        key = header
        if key in sections:
            # e.g. two "DIAGNOSIS:" blocks -> DIAGNOSIS, DIAGNOSIS (2)
            n = 2
            while f"{header} ({n})" in sections:
                n += 1
            key = f"{header} ({n})"
        sections[key] = body

    return sections


if __name__ == "__main__":
    demo = (
        "CHIEF COMPLAINT: Chest pain. HISTORY OF PRESENT ILLNESS: 54-year-old male "
        "with 2 hours of substernal chest pain. PAST MEDICAL HISTORY: Hypertension, "
        "diabetes. MEDICATIONS: Metformin 500 mg, Lisinopril 10 mg. ALLERGIES: "
        "Penicillin. ASSESSMENT: Acute coronary syndrome. PLAN: Admit to telemetry."
    )
    for k, v in split_sections(demo).items():
        print(f"[{k}] -> {v}")
