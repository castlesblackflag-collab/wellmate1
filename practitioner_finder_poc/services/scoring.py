"""
Deterministic weighted scoring for practitioner ranking.
"""

import logging

from practitioner_finder_poc.config.weights import (
    MAX_RADIUS_MILES,
    MAX_RATING,
    REVIEW_COUNT_SATURATION,
    SCORING_WEIGHTS,
)
from practitioner_finder_poc.services.symptom_mapping import compute_symptom_score
from practitioner_finder_poc.utils.geography import haversine_miles

logger = logging.getLogger(__name__)

# Preference weighting alignment: maps preference keywords to practitioner types
PREFERENCE_TYPE_ALIGNMENT = {
    "whole health": [
        "integrative medicine", "naturopath", "acupuncturist",
        "massage therapist", "chiropractor", "dietitian",
    ],
    "naturopathic": [
        "naturopath", "acupuncturist", "dietitian",
        "integrative medicine",
    ],
    "non-pharmacologic": [
        "physical therapist", "chiropractor", "acupuncturist",
        "massage therapist", "naturopath", "dietitian",
        "integrative medicine",
    ],
    "integrative": [
        "integrative medicine", "naturopath", "acupuncturist",
        "chiropractor", "dietitian",
    ],
    "conventional medical": [
        "general practitioner", "primary care", "anesthesiologist",
        "gastroenterologist", "pain clinic",
    ],
}

# Outcome-to-type soft alignment
OUTCOME_TYPE_ALIGNMENT = {
    "walking without pain": [
        "physical therapist", "pain clinic", "chiropractor",
        "acupuncturist", "integrative medicine",
    ],
    "avoiding long-term opioids": [
        "integrative medicine", "naturopath", "acupuncturist",
        "physical therapist", "chiropractor", "massage therapist",
    ],
    "improving digestion": [
        "gastroenterologist", "dietitian", "naturopath",
        "integrative medicine",
    ],
    "reducing stress": [
        "massage therapist", "acupuncturist", "naturopath",
        "integrative medicine", "chiropractor",
    ],
}


def score_practitioner(
    provider: dict,
    center_lat: float,
    center_lng: float,
    radius_miles: float,
    practitioner_types: list[str],
    symptoms: list[str],
    accessibility_prefs: list[str],
    preference_weights: list[str],
    preferred_outcomes: list[str],
    npi_result: dict,
) -> dict:
    """Score a single provider and return score breakdown.

    Args:
        provider: Normalized provider dict from extract_place_info
        center_lat, center_lng: Search center coordinates
        radius_miles: User-specified search radius
        practitioner_types: User-selected practitioner types
        symptoms: User-selected symptom keywords
        accessibility_prefs: User-selected accessibility preferences
        preference_weights: User-selected preference weightings
        preferred_outcomes: User-selected preferred outcomes
        npi_result: NPI query result dict

    Returns:
        dict with 'total_score', 'breakdown', and 'blurb'
    """
    breakdown = {}
    blurb_parts = []

    # 1. Practitioner type match
    type_score = _score_type_match(provider, practitioner_types)
    breakdown["practitioner_type_match"] = type_score
    if type_score > 0:
        blurb_parts.append("matches requested practitioner type")

    # 2. Geographic proximity
    geo_score = _score_proximity(provider, center_lat, center_lng, radius_miles)
    breakdown["geographic_proximity"] = geo_score

    # 3. Rating and reviews
    rating_score = _score_rating(provider)
    breakdown["rating_and_reviews"] = rating_score
    if provider.get("rating") and provider["rating"] >= 4.0:
        blurb_parts.append(f"rated {provider['rating']}/5")

    # 4. Accessibility preferences
    access_score = _score_accessibility(provider, accessibility_prefs)
    breakdown["accessibility_preferences"] = access_score
    access_notes = _accessibility_notes(provider, accessibility_prefs)
    blurb_parts.extend(access_notes)

    # 5. Symptom alignment (soft)
    symptom_score, symptom_reasons = compute_symptom_score(
        symptoms, practitioner_types,
        provider.get("types", []),
        provider.get("review_texts", []),
    )
    breakdown["symptom_alignment"] = symptom_score
    if symptom_reasons:
        blurb_parts.append(symptom_reasons[0])  # Include first reason

    # 6. Preference weighting
    pref_score = _score_preference_alignment(practitioner_types, preference_weights)
    breakdown["preference_weighting"] = pref_score
    if pref_score > 0.5:
        blurb_parts.append("aligns with care preferences")

    # 7. Preferred outcome (very soft)
    outcome_score = _score_outcome_alignment(practitioner_types, preferred_outcomes)
    breakdown["preferred_outcome"] = outcome_score

    # 8. NPI confidence
    npi_score = npi_result.get("confidence", 0.0)
    breakdown["npi_confidence"] = npi_score

    # Weighted total
    total = 0.0
    for key, weight in SCORING_WEIGHTS.items():
        total += weight * breakdown.get(key, 0.0)

    # Normalize to 0-100 scale
    total_score = round(total * 100, 1)

    blurb = "; ".join(blurb_parts) if blurb_parts else "general area match"

    return {
        "total_score": total_score,
        "breakdown": breakdown,
        "blurb": blurb,
    }


def _score_type_match(provider: dict, practitioner_types: list[str]) -> float:
    """Score based on how well provider types match requested types."""
    if not practitioner_types:
        return 0.5  # No preference = neutral

    provider_name = (provider.get("name") or "").lower()
    provider_place_types = [t.lower() for t in provider.get("types", [])]

    from practitioner_finder_poc.config.practitioner_types import PRACTITIONER_TYPES

    best = 0.0
    for pt in practitioner_types:
        info = PRACTITIONER_TYPES.get(pt, {})
        search_terms = info.get("search_terms", [pt])
        for term in search_terms:
            term_lower = term.lower()
            if term_lower in provider_name:
                best = max(best, 1.0)
            for place_type in provider_place_types:
                if term_lower in place_type or place_type in term_lower:
                    best = max(best, 0.8)
        # Check against Google place types
        pt_words = pt.lower().split()
        for word in pt_words:
            if len(word) > 3:
                for place_type in provider_place_types:
                    if word in place_type:
                        best = max(best, 0.6)
                if word in provider_name:
                    best = max(best, 0.7)

    return best


def _score_proximity(
    provider: dict, center_lat: float, center_lng: float, radius_miles: float
) -> float:
    """Score based on distance from search center. Closer = higher."""
    plat = provider.get("lat")
    plng = provider.get("lng")
    if plat is None or plng is None:
        return 0.3  # Unknown location = low but not zero

    dist = haversine_miles(center_lat, center_lng, plat, plng)
    max_r = min(radius_miles, MAX_RADIUS_MILES)
    if max_r <= 0:
        return 1.0
    score = max(0.0, 1.0 - (dist / max_r))
    return score


def _score_rating(provider: dict) -> float:
    """Score based on rating and review count."""
    rating = provider.get("rating")
    count = provider.get("review_count") or 0

    if rating is None:
        return 0.3  # No rating = low but not zero

    rating_component = rating / MAX_RATING
    count_component = min(count / REVIEW_COUNT_SATURATION, 1.0)

    return rating_component * 0.7 + count_component * 0.3


def _score_accessibility(provider: dict, prefs: list[str]) -> float:
    """Score based on accessibility/convenience preferences."""
    if not prefs:
        return 0.5

    hits = 0
    total = len(prefs)

    for pref in prefs:
        pref_lower = pref.lower()
        if "phone" in pref_lower and provider.get("phone"):
            hits += 1
        elif "website" in pref_lower and provider.get("website"):
            hits += 1
        elif "hours" in pref_lower and provider.get("hours"):
            hits += 1
        elif "telemedicine" in pref_lower:
            # Check for telemedicine clues in reviews or name
            name = (provider.get("name") or "").lower()
            reviews = " ".join(provider.get("review_texts", [])).lower()
            tele_keywords = ["telehealth", "telemedicine", "virtual", "online visit", "video visit"]
            if any(kw in name or kw in reviews for kw in tele_keywords):
                hits += 1

    return hits / total if total > 0 else 0.5


def _accessibility_notes(provider: dict, prefs: list[str]) -> list[str]:
    """Generate blurb notes about accessibility matches."""
    notes = []
    for pref in prefs:
        pref_lower = pref.lower()
        if "phone" in pref_lower and provider.get("phone"):
            notes.append("phone number listed")
        elif "website" in pref_lower and provider.get("website"):
            notes.append("website available")
        elif "hours" in pref_lower and provider.get("hours"):
            notes.append("hours listed")
    return notes


def _score_preference_alignment(
    practitioner_types: list[str], preference_weights: list[str]
) -> float:
    """Score how well practitioner types align with user care preferences."""
    if not preference_weights or not practitioner_types:
        return 0.5

    total_alignment = 0.0
    for pref in preference_weights:
        pref_lower = pref.lower().strip()
        aligned_types = PREFERENCE_TYPE_ALIGNMENT.get(pref_lower, [])
        if aligned_types:
            match_count = sum(1 for pt in practitioner_types if pt in aligned_types)
            if match_count > 0:
                total_alignment += match_count / len(practitioner_types)

    return min(total_alignment / len(preference_weights), 1.0)


def _score_outcome_alignment(
    practitioner_types: list[str], preferred_outcomes: list[str]
) -> float:
    """Very soft modifier based on preferred outcomes. Never exclusionary."""
    if not preferred_outcomes or not practitioner_types:
        return 0.5

    total = 0.0
    for outcome in preferred_outcomes:
        outcome_lower = outcome.lower().strip()
        aligned = OUTCOME_TYPE_ALIGNMENT.get(outcome_lower, [])
        if aligned:
            match_count = sum(1 for pt in practitioner_types if pt in aligned)
            if match_count > 0:
                total += match_count / len(practitioner_types)

    return min(total / len(preferred_outcomes), 1.0)
