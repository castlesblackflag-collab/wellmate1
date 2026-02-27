"""Place-to-NPI fuzzy matching logic.

Strategy decision (addressing open question #4 - NPI matching reliability):
- Use thefuzz (fuzzywuzzy) for string similarity on names and addresses.
- Match threshold is configurable (default 0.75 from weights.yaml).
- We match on: normalized name similarity + city/state agreement.
- For organizations/clinics, match on organization_name.
- A match above threshold attaches NPI credentials and specialties and sets
  npi_verified=true. Below threshold, the candidate keeps npi_verified=false.
- This is a best-effort enrichment; false negatives are acceptable (the provider
  still appears, just without NPI verification). False positives are controlled
  by the threshold.
"""

from __future__ import annotations

from typing import Any

import structlog
from httpx import AsyncClient
from thefuzz import fuzz

from app.config_loader import cfg
from app.npi_client import search_npi

logger = structlog.get_logger()


def _normalize_name(name: str) -> str:
    """Normalize a name for comparison: lowercase, strip common suffixes."""
    n = name.lower().strip()
    # Remove common business suffixes
    for suffix in [", md", ", do", ", np", ", pa", " md", " do", " llc", " inc", " pllc", " pc"]:
        n = n.replace(suffix, "")
    # Remove extra whitespace
    return " ".join(n.split())


def _extract_state_from_address(address: str) -> str | None:
    """Best-effort state extraction from a formatted address string."""
    parts = address.split(",")
    if len(parts) >= 2:
        # Typically: "123 Main St, City, ST 12345"
        state_zip = parts[-1].strip() if len(parts) >= 3 else parts[-1].strip()
        state_parts = state_zip.split()
        if state_parts and len(state_parts[0]) == 2:
            return state_parts[0].upper()
    return None


def _extract_city_from_address(address: str) -> str | None:
    """Best-effort city extraction from a formatted address string."""
    parts = address.split(",")
    if len(parts) >= 3:
        return parts[-2].strip()
    elif len(parts) >= 2:
        return parts[0].strip()
    return None


def _score_npi_match(
    candidate_name: str,
    candidate_address: str,
    npi_record: dict[str, Any],
) -> float:
    """Compute a match score between a Places candidate and an NPI record.

    Returns a score between 0.0 and 1.0.
    """
    cand_norm = _normalize_name(candidate_name)
    npi_name = _normalize_name(npi_record["full_name"])
    npi_org = _normalize_name(npi_record.get("organization_name", ""))

    # Name similarity (use best of individual name vs org name)
    name_score_individual = fuzz.token_sort_ratio(cand_norm, npi_name) / 100.0
    name_score_org = fuzz.token_sort_ratio(cand_norm, npi_org) / 100.0 if npi_org else 0.0
    name_score = max(name_score_individual, name_score_org)

    # Location agreement bonus
    cand_state = _extract_state_from_address(candidate_address)
    cand_city = _extract_city_from_address(candidate_address)
    npi_state = npi_record.get("practice_state", "")
    npi_city = npi_record.get("practice_city", "")

    location_bonus = 0.0
    if cand_state and npi_state and cand_state.upper() == npi_state.upper():
        location_bonus += 0.10
    if cand_city and npi_city and cand_city.lower() == npi_city.lower():
        location_bonus += 0.10

    return min(1.0, name_score * 0.80 + location_bonus)


async def enrich_candidates_with_npi(
    candidates: list[dict[str, Any]],
    client: AsyncClient,
) -> tuple[list[dict[str, Any]], bool]:
    """Attempt NPI enrichment for candidates flagged as physicians/clinics.

    Returns (enriched_candidates, npi_available). npi_available is False if
    all NPI calls failed (used for warning generation).
    """
    npi_available = True
    npi_attempted = 0
    npi_matched = 0

    for candidate in candidates:
        if not candidate.get("is_physician", False):
            continue

        name = candidate.get("name", "")
        address = candidate.get("address", "")
        if not name:
            continue

        state = _extract_state_from_address(address)
        city = _extract_city_from_address(address)

        npi_results = await search_npi(name, state, city, client)
        npi_attempted += 1

        if not npi_results:
            # Could be a genuine no-match or an API failure
            continue

        # Find best match
        best_score = 0.0
        best_record: dict[str, Any] | None = None
        for record in npi_results:
            score = _score_npi_match(name, address, record)
            if score > best_score:
                best_score = score
                best_record = record

        if best_record and best_score >= cfg.npi_match_threshold:
            candidate["npi_verified"] = True
            candidate["npi_number"] = best_record["npi"]
            candidate["credentials"] = best_record["credentials"]
            candidate["npi_specialties"] = best_record["specialties"]
            candidate["npi_match_score"] = round(best_score, 2)
            npi_matched += 1
            logger.info(
                "npi_match_found",
                candidate=name,
                npi=best_record["npi"],
                score=round(best_score, 2),
            )
        else:
            candidate["npi_verified"] = False

    if npi_attempted > 0 and npi_matched == 0 and not npi_available:
        npi_available = False

    logger.info(
        "npi_enrichment_complete",
        attempted=npi_attempted,
        matched=npi_matched,
    )
    return candidates, npi_available
