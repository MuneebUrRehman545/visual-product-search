import re
from typing import Dict, List


# ==========================================================
# Configuration
# ==========================================================

# Below this groundedness score, flag the answer as
# potentially hallucinated.
GROUNDEDNESS_THRESHOLD = 0.6

# Answers matching these patterns are refusals ΓÇö they make
# no factual claims, so groundedness checking doesn't apply.
REFUSAL_PATTERNS = [
    "couldn't find that information",
    "could not find that information",
    "couldn't determine which",
    "can't provide sensitive",
    "cannot provide sensitive",
    "temporarily unavailable",
]


# ==========================================================
# Claim Extraction
# ==========================================================

def _extract_claims(answer: str) -> List[str]:
    """
    Extract checkable "claims" from a generated answer:
    numbers (dates, amounts, IDs) and capitalized words that
    are not the first word of a sentence (likely proper
    nouns ΓÇö names, companies, places).

    These are the kinds of specific facts an LLM is most
    likely to invent when it hallucinates, and the kinds of
    facts that should be traceable back to source text
    verbatim if the answer is properly grounded.
    """

    claims = []

    # Numbers (amounts, dates, percentages, IDs)
    numbers = re.findall(r"\b\d[\d,.]*%?\b", answer)
    claims.extend(numbers)

    # Capitalized words not at the start of a sentence
    sentences = re.split(r"(?<=[.!?])\s+", answer)

    for sentence in sentences:

        words = sentence.split()

        for index, word in enumerate(words):

            cleaned = re.sub(r"[^\w]", "", word)

            if not cleaned or len(cleaned) < 3:
                continue

            # Skip the first word of the sentence ΓÇö capitalized
            # purely due to sentence-start grammar, not because
            # it's a proper noun.
            if index == 0:
                continue

            if cleaned[0].isupper():
                claims.append(cleaned)

    # De-duplicate, case-sensitive (names matter)
    return list(dict.fromkeys(claims))


# ==========================================================
# Groundedness Check
# ==========================================================

def check_groundedness(answer: str, context: str) -> Dict:
    """
    Rule-based hallucination check.

    Extracts factual claims (numbers, proper nouns) from the
    generated answer and checks what fraction of them appear
    verbatim in the retrieved context. A low score suggests
    the model may have introduced facts not present in the
    source material.

    This is a heuristic signal, not a guarantee ΓÇö it can miss
    paraphrased hallucinations and can false-flag legitimate
    inference (e.g. summarizing "$50,000 and $30,000" as
    "$80,000 total"). It's intended as a lightweight, zero-
    cost first-pass filter, not a replacement for the manual
    citation-accuracy review.
    """

    answer_lower_check = answer.lower().strip()

    is_refusal = any(
        pattern in answer_lower_check
        for pattern in REFUSAL_PATTERNS
    )

    if is_refusal:
        return {
            "checked": False,
            "reason": "refusal_answer",
            "groundedness_score": None,
            "flagged": False,
            "claims_checked": [],
            "claims_missing": [],
        }

    claims = _extract_claims(answer)

    if not claims:
        return {
            "checked": False,
            "reason": "no_checkable_claims",
            "groundedness_score": None,
            "flagged": False,
            "claims_checked": [],
            "claims_missing": [],
        }

    context_lower = context.lower()

    missing = [
        claim
        for claim in claims
        if claim.lower() not in context_lower
    ]

    found_count = len(claims) - len(missing)
    score = found_count / len(claims)

    return {
        "checked": True,
        "reason": None,
        "groundedness_score": round(score, 2),
        "flagged": score < GROUNDEDNESS_THRESHOLD,
        "claims_checked": claims,
        "claims_missing": missing,
    }
