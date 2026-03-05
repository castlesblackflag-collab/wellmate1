"""Deterministic scoring engine and fit reason generator.

Scoring priority (highest to lowest, must dominate):
  1. Access / Existence: prefer valid, complete candidates
  2. Accessibility: distance and telehealth
  3. Contact availability: phone > website > neither
  4. Review quality: rating * log(review_count)
  5. Preference / Avoidance alignment
  6. Care style alignment
  7. Symptom alignment
  8. Outcome alignment

Weights are loaded from weights.yaml and can be tuned without code changes.
Fit reasons are templated strings tied to the top scoring drivers.
"""

from __future__ import annotations

import math
from typing import Any

from app.config_loader import cfg

# Medical categories that count as "medical" care alignment
_MEDICAL_CATEGORIES = {"physician", "clinic", "physical_therapy"}
# Whole-health categories
_WHOLE_HEALTH_CATEGORIES = {
    "acupuncture", "yoga", "meditation", "massage",
    "nutrition", "counseling", "chiropractic",
}


def _keyword_overlap(text_tokens: set[str], reference_terms: list[str]) -> float:
    """Compute overlap score between a set of tokens and reference terms.

    Returns a value in [0, 1] based on fraction of reference terms that
    have at least a partial match in the text tokens.
    """
    if not reference_terms:
        return 0.0
    matches = 0
    for term in reference_terms:
        term_lower = term.lower()
        term_words = set(term_lower.split())
        if term_words & text_tokens:
            matches += 1
        elif any(tw in token for token in text_tokens for tw in term_words):
            matches += 0.5
    return min(1.0, matches / len(reference_terms))


def _compute_data_completeness(candidate: dict[str, Any]) -> float:
    """Score how complete/valid a candidate's data is.

    Rewards candidates with name, address, rating, review count, phone, website.
    """
    score = 0.0
    max_points = 6.0

    if candidate.get("name"):
        score += 1.0
    if candidate.get("address"):
        score += 1.0
    if candidate.get("rating") is not None:
        score += 1.0
    if candidate.get("review_count") is not None and candidate["review_count"] > 0:
        score += 1.0
    if candidate.get("phone"):
        score += 1.0
    if candidate.get("website"):
        score += 1.0

    return (score / max_points) * 100.0


def _compute_accessibility(
    candidate: dict[str, Any],
    radius_km: int,
    visit_mode: str,
) -> float:
    """Score based on distance and visit mode compatibility."""
    score = 50.0

    # Distance component
    distance = candidate.get("distance_km")
    if distance is not None and radius_km > 0:
        # Closer is better: linear decay from 100 at 0km to 0 at radius
        distance_score = max(0.0, 1.0 - distance / radius_km) * 100.0
        score = distance_score * 0.7 + 30.0  # 30 baseline + 70 from distance
    else:
        score = 40.0  # Unknown distance

    # Visit mode: we don't have reliable telehealth data from Places,
    # so this is a minor signal.
    if visit_mode == "telehealth":
        score = max(score, 50.0)

    return min(100.0, max(0.0, score))


def _compute_contact_availability(candidate: dict[str, Any]) -> float:
    """Score based on availability of contact information.

    Phone number present => strong positive.
    Website present => positive.
    """
    score = 0.0
    if candidate.get("phone"):
        score += 65.0
    if candidate.get("website"):
        score += 35.0
    return score


def _compute_review_quality(candidate: dict[str, Any]) -> float:
    """Score based on rating and review count.

    Uses rating * log(review_count + 1) normalized to [0, 100].
    """
    rating = candidate.get("rating")
    review_count = candidate.get("review_count")

    if rating is None:
        return 30.0  # No data: below average default

    # Normalize rating to [0, 1] (ratings are 1-5)
    rating_norm = max(0.0, (rating - 1.0) / 4.0)

    # Log-scaled review count factor
    count = review_count or 0
    count_factor = min(1.0, math.log(count + 1) / math.log(200))

    # Combined: 70% rating, 30% volume
    combined = rating_norm * 0.70 + count_factor * 0.30
    return combined * 100.0


def _compute_preference_alignment(
    preferences: list[str],
    avoidances: list[str],
    candidate: dict[str, Any],
) -> float:
    """Score preference boosts and avoidance penalties."""
    if not preferences and not avoidances:
        return 50.0  # Neutral

    category = candidate.get("category", "other")
    score = 50.0

    for pref in preferences:
        pref_lower = pref.lower()
        for pref_key, signals in cfg.preference_signals.items():
            if pref_key in pref_lower:
                boosts = signals.get("boosts", [])
                if category in boosts:
                    score += 25.0
                    break

    for avoid in avoidances:
        avoid_lower = avoid.lower()
        if avoid_lower in ("medication", "opioids", "drugs"):
            if category in _WHOLE_HEALTH_CATEGORIES:
                score += 15.0
        if avoid_lower == "surgery":
            if category in _WHOLE_HEALTH_CATEGORIES:
                score += 15.0

    return min(100.0, max(0.0, score))


def _compute_care_style_alignment(
    provider_scope: str,
    candidate: dict[str, Any],
) -> float:
    """Score how well the candidate's category matches the requested provider scope."""
    category = candidate.get("category", "other")

    if provider_scope == "medical":
        if category in _MEDICAL_CATEGORIES:
            return 100.0
        if candidate.get("is_physician", False):
            return 100.0
        return 20.0

    if provider_scope == "whole_health":
        if category in _WHOLE_HEALTH_CATEGORIES:
            return 100.0
        return 20.0

    # medical_and_whole_health: both are welcome
    if category in _MEDICAL_CATEGORIES or category in _WHOLE_HEALTH_CATEGORIES:
        return 80.0
    return 50.0


def _compute_symptom_alignment(
    main_issue: str | None,
    candidate: dict[str, Any],
) -> float:
    """Score symptom alignment using symptom_to_specialties config."""
    if not main_issue:
        return 50.0  # Neutral if no symptom info

    candidate_specialties = set()
    for s in candidate.get("npi_specialties", []):
        candidate_specialties.update(s.lower().split())
    candidate_specialties.add(candidate.get("category", "").lower())
    if candidate.get("query_used"):
        candidate_specialties.update(candidate["query_used"].lower().split())

    term = main_issue.lower()
    for symptom_key, specs in cfg.symptom_to_specialties.items():
        if symptom_key in term:
            spec_words = set()
            for spec in specs:
                spec_words.update(spec.lower().split())
            if spec_words & candidate_specialties:
                return 100.0

    # Fallback: direct keyword overlap
    term_words = set(term.split())
    if term_words & candidate_specialties:
        return 50.0

    return 30.0


def _compute_outcome_alignment(
    goal_outcomes: list[str],
    candidate: dict[str, Any],
) -> float:
    """Score how well a candidate's specialties/modalities align with user outcomes."""
    if not goal_outcomes:
        return 50.0  # Neutral if no outcomes specified

    candidate_category = candidate.get("category", "other")
    candidate_specialties = [s.lower() for s in candidate.get("npi_specialties", [])]
    candidate_types = [t.lower() for t in candidate.get("types", [])]

    candidate_signals = set()
    candidate_signals.add(candidate_category.lower())
    candidate_signals.update(candidate_specialties)
    candidate_signals.update(candidate_types)
    if candidate.get("query_used"):
        candidate_signals.update(candidate["query_used"].lower().split())

    total_score = 0.0
    outcome_count = 0

    for outcome in goal_outcomes:
        outcome_lower = outcome.lower()
        best_match = 0.0

        for keyword, modal_map in cfg.outcome_to_modalities.items():
            if keyword in outcome_lower:
                relevant = []
                for style_key in ("medical", "whole_health"):
                    relevant.extend(modal_map.get(style_key, []))

                for modality in relevant:
                    mod_lower = modality.lower()
                    mod_words = set(mod_lower.split())
                    if mod_words & candidate_signals:
                        best_match = max(best_match, 1.0)
                    elif any(mw in sig for sig in candidate_signals for mw in mod_words):
                        best_match = max(best_match, 0.6)

        outcome_words = set(outcome_lower.split())
        if outcome_words & candidate_signals:
            best_match = max(best_match, 0.7)

        total_score += best_match
        outcome_count += 1

    if outcome_count == 0:
        return 50.0

    return (total_score / outcome_count) * 100.0


def score_candidate(
    candidate: dict[str, Any],
    goal_outcomes: list[str],
    main_issue: str | None,
    provider_scope: str,
    preferences: list[str],
    avoidances: list[str],
    visit_mode: str,
    radius_km: int,
) -> tuple[int, dict[str, float]]:
    """Compute composite score for a single candidate.

    Returns (score_0_to_100, sub_scores_dict).
    """
    sub_scores = {
        "data_completeness": _compute_data_completeness(candidate),
        "accessibility": _compute_accessibility(candidate, radius_km, visit_mode),
        "contact_availability": _compute_contact_availability(candidate),
        "review_quality": _compute_review_quality(candidate),
        "preference_alignment": _compute_preference_alignment(preferences, avoidances, candidate),
        "care_style_alignment": _compute_care_style_alignment(provider_scope, candidate),
        "symptom_alignment": _compute_symptom_alignment(main_issue, candidate),
        "outcome_alignment": _compute_outcome_alignment(goal_outcomes, candidate),
    }

    weighted_total = (
        cfg.w_data_completeness * sub_scores["data_completeness"]
        + cfg.w_accessibility * sub_scores["accessibility"]
        + cfg.w_contact * sub_scores["contact_availability"]
        + cfg.w_review * sub_scores["review_quality"]
        + cfg.w_preference * sub_scores["preference_alignment"]
        + cfg.w_care_style * sub_scores["care_style_alignment"]
        + cfg.w_symptom * sub_scores["symptom_alignment"]
        + cfg.w_outcome * sub_scores["outcome_alignment"]
    )

    final_score = max(0, min(100, round(weighted_total)))
    return final_score, sub_scores


def generate_fit_reasons(
    candidate: dict[str, Any],
    sub_scores: dict[str, float],
    goal_outcomes: list[str],
    preferences: list[str],
    avoidances: list[str],
) -> list[str]:
    """Generate 2-5 templated fit reason strings from sub-score contributions.

    Reasons reflect the top scoring drivers in priority order:
    access > accessibility > contact > review > preference > care style > symptom > outcome.
    """
    reasons: list[str] = []

    # 1. Accessibility reason (distance)
    distance = candidate.get("distance_km")
    if distance is not None and distance <= 5.0:
        reasons.append(f"Located {distance} km away")
    elif distance is not None:
        reasons.append(f"Located {distance} km from your location")

    # 2. Contact availability reasons
    if candidate.get("phone"):
        reasons.append("Phone number available for booking")
    if candidate.get("website") and not candidate.get("phone"):
        reasons.append("Website available for information")

    # 3. Review quality reason
    if sub_scores["review_quality"] >= 55.0:
        rating = candidate.get("rating")
        count = candidate.get("review_count")
        if rating and count and count >= 200:
            reasons.append(f"High review signal: {rating} with {count}+ reviews")
        elif rating and count:
            reasons.append(f"Rated {rating} stars ({count} reviews)")
        elif rating:
            reasons.append(f"Rated {rating} stars")

    # 4. Preference alignment reasons
    if sub_scores["preference_alignment"] >= 60.0 and preferences:
        for pref in preferences[:1]:
            reasons.append(f"Matches preference: {pref}")

    # 5. Avoidance acknowledgment
    category = candidate.get("category", "other")
    if avoidances and category in _WHOLE_HEALTH_CATEGORIES:
        reasons.append("Non-pharmacologic approach")

    # 6. Care style reason
    if sub_scores["care_style_alignment"] >= 70.0:
        if category in _MEDICAL_CATEGORIES:
            reasons.append("Provides medical/clinical care")
        elif category in _WHOLE_HEALTH_CATEGORIES:
            reasons.append(f"Offers {category.replace('_', ' ')} services")

    # 7. Outcome alignment reasons
    if sub_scores["outcome_alignment"] >= 60.0 and goal_outcomes:
        for outcome in goal_outcomes[:1]:
            reasons.append(f"Matches goal: {outcome}")

    # 8. NPI verification
    if candidate.get("npi_verified"):
        creds = candidate.get("credentials", [])
        if creds:
            reasons.append(f"Verified credentials: {', '.join(creds[:3])}")
        else:
            reasons.append("NPI-verified provider")

    # Ensure at least 2 reasons
    if len(reasons) < 2:
        if candidate.get("is_physician"):
            reasons.append("Licensed healthcare provider")
        else:
            reasons.append("Relevant provider in your area")

    if len(reasons) < 2:
        reasons.append("Relevant provider in your area")

    # Cap at 5
    return reasons[:5]


def score_and_rank_candidates(
    candidates: list[dict[str, Any]],
    goal_outcomes: list[str],
    main_issue: str | None,
    provider_scope: str,
    preferences: list[str],
    avoidances: list[str],
    visit_mode: str,
    radius_km: int,
    max_results: int,
) -> list[dict[str, Any]]:
    """Score all candidates, generate fit reasons, sort by score, return top N."""
    scored: list[dict[str, Any]] = []

    for candidate in candidates:
        score, sub_scores = score_candidate(
            candidate=candidate,
            goal_outcomes=goal_outcomes,
            main_issue=main_issue,
            provider_scope=provider_scope,
            preferences=preferences,
            avoidances=avoidances,
            visit_mode=visit_mode,
            radius_km=radius_km,
        )
        fit_reasons = generate_fit_reasons(
            candidate=candidate,
            sub_scores=sub_scores,
            goal_outcomes=goal_outcomes,
            preferences=preferences,
            avoidances=avoidances,
        )
        candidate["score"] = score
        candidate["fit_reasons"] = fit_reasons
        candidate["sub_scores"] = sub_scores
        scored.append(candidate)

    # Sort by score descending, then by review quality as tiebreaker
    scored.sort(key=lambda c: (c["score"], c.get("rating") or 0), reverse=True)

    return scored[:max_results]
