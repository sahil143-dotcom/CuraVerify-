"""Controlled hallucination generation for eval (data curation loop)."""
from __future__ import annotations

import random
import re
import sys
from typing import List, Optional, Tuple

from . import config, db
from .segment import split_sentences

_METHODS = [
    "CRISPR-Cas9",
    "RNA-seq",
    "BERT",
    "random forest",
    "logistic regression",
    "GWAS",
    "ELISA",
]
_DATASETS = ["ImageNet", "UK Biobank", "TCGA", "MIMIC-IV", "Gene Ontology"]
_FACTS = [
    "The study also reports a 99.9% cure rate in all patients within 24 hours.",
    "Authors claim the method works perfectly on every human population without side effects.",
    "The paper proves faster-than-light signaling in clinical imaging pipelines.",
]


def _bump_number(text: str, rng: random.Random) -> Optional[str]:
    matches = list(re.finditer(r"(\d+(?:\.\d+)?)(\s*(?:%|percent))?", text))
    if not matches:
        return None
    m = rng.choice(matches)
    val = float(m.group(1))
    unit = m.group(2) or ""
    factor = rng.uniform(1.15, 1.45)
    new_val = val * factor
    if val >= 10 and "." not in m.group(1):
        repl = f"{int(round(new_val))}{unit}"
    else:
        repl = f"{new_val:.1f}{unit}"
    return text[: m.start()] + repl + text[m.end() :]


def perturb_summary(summary: str, ptype: str, rng: random.Random) -> Tuple[str, str]:
    """Return (rewritten_summary, explanation)."""
    sents = split_sentences(summary)
    if not sents:
        return summary, "empty"

    idx = rng.randrange(len(sents))
    original = sents[idx]
    new = original
    explanation = ptype

    if ptype == "wrong_value":
        bumped = _bump_number(original, rng)
        if bumped:
            new = bumped
            explanation = "Changed a numeric value by >15%."
        else:
            # Fallback invented number
            new = original.rstrip(".") + f", increasing outcomes by {rng.randint(25, 80)}%."
            explanation = "Injected an unsupported numeric gain."
    elif ptype == "wrong_method":
        method = rng.choice(_METHODS)
        new = re.sub(
            r"\b(using|via|with|by)\b",
            f"using {method} via",
            original,
            count=1,
            flags=re.IGNORECASE,
        )
        if new == original:
            new = f"Using {method}, " + original[0].lower() + original[1:]
        explanation = f"Attributed result to method '{method}'."
    elif ptype == "wrong_attribution":
        new = original.rstrip(".") + " as first demonstrated by Smith et al. (1999)."
        explanation = "Added a false attribution."
    elif ptype == "missing_context":
        # Drop hedging / subset qualifiers
        new = re.sub(
            r"\b(in (a )?subset|among women|in mice|in vitro|on average|approximately|roughly)\b[, ]*",
            "",
            original,
            flags=re.IGNORECASE,
        )
        if new == original:
            new = re.sub(r"\b(may|might|could|suggests?)\b", "does", original, flags=re.IGNORECASE)
        explanation = "Removed important qualifier / hedging."
    elif ptype == "invented_fact":
        fact = rng.choice(_FACTS)
        # Insert after chosen sentence
        sents = sents[: idx + 1] + [fact] + sents[idx + 1 :]
        return " ".join(sents), f"Inserted invented fact: {fact}"
    else:
        explanation = "unknown type"

    sents[idx] = new
    return " ".join(sents), explanation


def generate_hallucinated(
    n: int = 50,
    seed: int = 42,
) -> dict:
    config.ensure_dirs()
    rng = random.Random(seed)
    conn = db.connect()
    try:
        db.init_db(conn)
        rows = conn.execute(
            """
            SELECT s.id AS summary_id, s.paper_id, s.summary_text
            FROM summaries s
            WHERE s.is_real = 1
              AND s.perturbation_type IS NULL
            ORDER BY s.id
            """
        ).fetchall()
        if not rows:
            raise SystemExit("No real summaries in DB. Run load_biolaysumm first.")

        # Prefer validation papers if available via join
        val_rows = conn.execute(
            """
            SELECT s.id AS summary_id, s.paper_id, s.summary_text
            FROM summaries s
            JOIN papers p ON p.id = s.paper_id
            WHERE s.is_real = 1 AND p.split LIKE '%validation%'
            ORDER BY s.id
            """
        ).fetchall()
        pool = list(val_rows) if len(val_rows) >= n else list(rows)
        rng.shuffle(pool)
        chosen = pool[:n]

        created = 0
        by_type = {t: 0 for t in config.HALLUCINATION_TYPES}
        for i, row in enumerate(chosen):
            ptype = config.HALLUCINATION_TYPES[i % len(config.HALLUCINATION_TYPES)]
            rewritten, _expl = perturb_summary(row["summary_text"], ptype, rng)
            db.insert_summary(
                conn,
                {
                    "paper_id": row["paper_id"],
                    "summary_text": rewritten,
                    "is_real": 0,
                    "source": "llm_rewritten",
                    "perturbation_type": ptype,
                },
            )
            by_type[ptype] += 1
            created += 1

        return {
            "created": created,
            "by_type": by_type,
            "total_summaries": db.count_summaries(conn),
            "hallucinated": db.count_summaries(conn, real_only=False),
        }
    finally:
        conn.close()


def main() -> None:
    n = config.DEFAULT_HALLUCINATE_N
    for i, arg in enumerate(sys.argv):
        if arg == "--n" and i + 1 < len(sys.argv):
            n = int(sys.argv[i + 1])
    stats = generate_hallucinated(n=n)
    print("[hallucinate]", stats)


if __name__ == "__main__":
    main()
