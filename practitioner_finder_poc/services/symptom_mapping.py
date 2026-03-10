"""
Symptom-to-practitioner soft matching.

This is a soft ranking signal only. It never excludes providers.
"""

# Mapping of symptom keywords to practitioner types and review keywords
# that hint at relevance. Used for soft boosting only.
SYMPTOM_SIGNALS = {
    "pain": {
        "type_hints": [
            "physical therapist", "chiropractor", "acupuncturist",
            "pain clinic", "anesthesiologist", "integrative medicine",
            "massage therapist",
        ],
        "review_keywords": [
            "pain", "chronic pain", "back pain", "joint", "injury",
            "relief", "mobility",
        ],
    },
    "addiction": {
        "type_hints": [
            "general practitioner", "primary care", "integrative medicine",
            "naturopath",
        ],
        "review_keywords": [
            "addiction", "recovery", "substance", "opioid", "dependence",
            "sober", "withdrawal",
        ],
    },
    "gastrointestinal distress": {
        "type_hints": [
            "gastroenterologist", "dietitian", "naturopath",
            "integrative medicine", "primary care",
        ],
        "review_keywords": [
            "stomach", "digestive", "gastro", "ibs", "bloating",
            "gut", "intestinal", "nausea", "acid reflux",
        ],
    },
    "fatigue": {
        "type_hints": [
            "primary care", "general practitioner", "integrative medicine",
            "naturopath", "dietitian",
        ],
        "review_keywords": [
            "fatigue", "tired", "energy", "exhaustion", "sleep",
        ],
    },
    "anxiety": {
        "type_hints": [
            "primary care", "general practitioner", "integrative medicine",
            "naturopath", "acupuncturist", "massage therapist",
        ],
        "review_keywords": [
            "anxiety", "stress", "nervous", "calm", "relaxation",
            "mental health",
        ],
    },
    "inflammation": {
        "type_hints": [
            "integrative medicine", "naturopath", "dietitian",
            "chiropractor", "acupuncturist", "primary care",
        ],
        "review_keywords": [
            "inflammation", "anti-inflammatory", "swelling", "autoimmune",
            "joint pain",
        ],
    },
}


def compute_symptom_score(
    symptoms: list[str],
    practitioner_types_selected: list[str],
    provider_types: list[str],
    review_texts: list[str],
) -> tuple[float, list[str]]:
    """Compute a symptom alignment score and matching reasons.

    Args:
        symptoms: User-selected symptom keywords
        practitioner_types_selected: User-selected practitioner types
        provider_types: Google Places 'types' for this provider
        review_texts: Review text snippets for this provider

    Returns:
        (score, reasons) where score is 0.0-1.0 and reasons is a list
        of human-readable match hints.
    """
    if not symptoms:
        return 0.0, []

    total_score = 0.0
    reasons = []
    combined_reviews = " ".join(review_texts).lower()

    for symptom in symptoms:
        symptom_key = symptom.lower().strip()
        signals = SYMPTOM_SIGNALS.get(symptom_key, {})
        if not signals:
            continue

        type_hints = signals.get("type_hints", [])
        review_keywords = signals.get("review_keywords", [])

        # Type alignment
        type_match = any(pt in type_hints for pt in practitioner_types_selected)
        if type_match:
            total_score += 0.4
            reasons.append(f"practitioner type may be relevant for {symptom}")

        # Review keyword alignment
        if combined_reviews:
            keyword_hits = sum(1 for kw in review_keywords if kw in combined_reviews)
            if keyword_hits > 0:
                review_boost = min(keyword_hits * 0.15, 0.5)
                total_score += review_boost
                reasons.append(f"reviews mention terms related to {symptom}")

    # Normalize to 0-1
    max_possible = len(symptoms) * 0.9
    if max_possible > 0:
        total_score = min(total_score / max_possible, 1.0)

    return total_score, reasons
