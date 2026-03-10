"""
NPPES NPI Registry cross-referencing.

Only attempts matching for likely medical providers.
Uses conservative matching: name + state + taxonomy hint.
"""

import logging
import re

import httpx

from practitioner_finder_poc.config.practitioner_types import PRACTITIONER_TYPES

logger = logging.getLogger(__name__)

_NPI_API = "https://npiregistry.cms.hhs.gov/api/"


def is_npi_eligible(practitioner_types: list[str]) -> bool:
    """Check if any of the selected practitioner types are NPI-eligible."""
    for pt in practitioner_types:
        info = PRACTITIONER_TYPES.get(pt, {})
        if info.get("npi_eligible"):
            return True
    return False


def get_taxonomy_hints(practitioner_types: list[str]) -> list[str]:
    """Get taxonomy search hints for selected practitioner types."""
    hints = []
    for pt in practitioner_types:
        info = PRACTITIONER_TYPES.get(pt, {})
        hint = info.get("npi_taxonomy_hint")
        if hint:
            hints.append(hint)
    return hints


def _extract_name_parts(place_name: str) -> tuple[str, str]:
    """Try to extract a first and last name from a place name.

    Very conservative: only works for names like "Dr. John Smith" or "Smith, John".
    Returns ("", "") if extraction is not confident.
    """
    cleaned = re.sub(r"\b(Dr\.?|MD|DO|DPT|RD|DC|PhD|FACS|PA-C|NP|RN)\b", "", place_name, flags=re.IGNORECASE)
    cleaned = re.sub(r"[,.\-]+", " ", cleaned).strip()
    parts = cleaned.split()

    if len(parts) == 2:
        return (parts[0], parts[1])
    if len(parts) == 3:
        return (parts[0], parts[2])
    return ("", "")


def _extract_state_from_address(address: str | None) -> str:
    """Try to extract a 2-letter US state code from an address string."""
    if not address:
        return ""
    match = re.search(r"\b([A-Z]{2})\s+\d{5}", address)
    if match:
        return match.group(1)
    return ""


def query_npi(
    place_name: str,
    address: str | None,
    practitioner_types: list[str],
) -> dict:
    """Query the NPI registry for a place.

    Returns a dict with:
        - status: "NPI matched" | "possible NPI match" | "no API match available"
        - npi_number: str | None
        - npi_name: str | None
        - taxonomy: str | None
        - confidence: float (0.0 to 1.0)
    """
    result = {
        "status": "no API match available",
        "npi_number": None,
        "npi_name": None,
        "taxonomy": None,
        "confidence": 0.0,
    }

    if not is_npi_eligible(practitioner_types):
        return result

    state = _extract_state_from_address(address)
    first_name, last_name = _extract_name_parts(place_name)
    taxonomy_hints = get_taxonomy_hints(practitioner_types)

    # Try individual provider search if we have name parts
    if last_name:
        try:
            params = {
                "version": "2.1",
                "limit": 5,
                "last_name": last_name,
            }
            if first_name:
                params["first_name"] = first_name
            if state:
                params["state"] = state

            resp = httpx.get(_NPI_API, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if results:
                best = _pick_best_match(results, taxonomy_hints, place_name)
                if best:
                    return best
        except Exception:
            logger.exception("NPI individual search failed for %s", place_name)

    # Try organization search using full place name
    try:
        org_name = re.sub(r"\b(Dr\.?|MD|DO)\b", "", place_name, flags=re.IGNORECASE).strip()
        if len(org_name) > 3:
            params = {
                "version": "2.1",
                "limit": 5,
                "organization_name": org_name,
            }
            if state:
                params["state"] = state

            resp = httpx.get(_NPI_API, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if results:
                best = _pick_best_match(results, taxonomy_hints, place_name)
                if best:
                    return best
    except Exception:
        logger.exception("NPI organization search failed for %s", place_name)

    return result


def _pick_best_match(
    results: list[dict],
    taxonomy_hints: list[str],
    original_name: str,
) -> dict | None:
    """Pick the best NPI match from results, if any is good enough."""
    original_lower = original_name.lower()

    for r in results:
        basic = r.get("basic", {})
        npi = str(r.get("number", ""))
        taxonomies = r.get("taxonomies", [])

        # Build a name string for comparison
        org_name = basic.get("organization_name", "")
        first = basic.get("first_name", "")
        last = basic.get("last_name", "")
        npi_name = org_name if org_name else f"{first} {last}".strip()
        npi_lower = npi_name.lower()

        # Check taxonomy match
        taxonomy_match = False
        taxonomy_desc = None
        for t in taxonomies:
            desc = (t.get("desc", "") or "").lower()
            taxonomy_desc = t.get("desc")
            for hint in taxonomy_hints:
                if hint.lower() in desc:
                    taxonomy_match = True
                    break
            if taxonomy_match:
                break
        if not taxonomy_desc and taxonomies:
            taxonomy_desc = taxonomies[0].get("desc")

        # Determine match quality
        name_overlap = _name_similarity(original_lower, npi_lower)

        if name_overlap > 0.7 and taxonomy_match:
            return {
                "status": "NPI matched",
                "npi_number": npi,
                "npi_name": npi_name,
                "taxonomy": taxonomy_desc,
                "confidence": 0.9,
            }
        if name_overlap > 0.5 or taxonomy_match:
            return {
                "status": "possible NPI match",
                "npi_number": npi,
                "npi_name": npi_name,
                "taxonomy": taxonomy_desc,
                "confidence": 0.5,
            }

    return None


def _name_similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity between two name strings."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0
