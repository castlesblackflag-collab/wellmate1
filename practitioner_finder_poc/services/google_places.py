"""
Google Places API (New) client.

Uses the Places API (New) endpoints:
  - searchNearby for candidate discovery
  - places/{id} for detail fetching
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://places.googleapis.com/v1"

# Field masks for Nearby Search
_SEARCH_FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.location,"
    "places.types,"
    "places.rating,"
    "places.userRatingCount,"
    "places.nationalPhoneNumber,"
    "places.websiteUri,"
    "places.currentOpeningHours,"
    "places.regularOpeningHours"
)

# Field mask for Place Details (includes reviews)
_DETAILS_FIELD_MASK = (
    "id,"
    "displayName,"
    "formattedAddress,"
    "location,"
    "types,"
    "rating,"
    "userRatingCount,"
    "nationalPhoneNumber,"
    "websiteUri,"
    "currentOpeningHours,"
    "regularOpeningHours,"
    "reviews"
)


def _get_api_key() -> str:
    key = os.environ.get("PLACES_API_KEY", "")
    if not key:
        logger.warning("PLACES_API_KEY not set; API calls will fail")
    return key


def search_nearby(
    lat: float,
    lng: float,
    radius_miles: float,
    search_terms: list[str],
    max_results: int = 20,
) -> list[dict]:
    """Search for places near a location using Places API (New) searchNearby.

    Returns a list of place dicts (raw API shape).
    """
    api_key = _get_api_key()
    if not api_key:
        return []

    radius_meters = min(radius_miles * 1609.34, 50000)  # API max 50km

    all_places: dict[str, dict] = {}

    for term in search_terms:
        body = {
            "textQuery": term,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": radius_meters,
                }
            },
            "maxResultCount": min(max_results, 20),
        }

        try:
            resp = httpx.post(
                f"{_BASE}/places:searchText",
                json=body,
                headers={
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": _SEARCH_FIELD_MASK,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            for place in data.get("places", []):
                pid = place.get("id")
                if pid and pid not in all_places:
                    all_places[pid] = place
        except Exception:
            logger.exception("Places searchText failed for term '%s'", term)

    return list(all_places.values())


def get_place_details(place_id: str) -> dict | None:
    """Fetch full details for a single place (including reviews)."""
    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        resp = httpx.get(
            f"{_BASE}/places/{place_id}",
            headers={
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": _DETAILS_FIELD_MASK,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception("Place details fetch failed for %s", place_id)
        return None


def extract_place_info(place: dict) -> dict:
    """Normalize a Places API response into a flat dict for scoring."""
    display_name = place.get("displayName", {})
    name = display_name.get("text", "Unknown") if isinstance(display_name, dict) else str(display_name)

    location = place.get("location", {})

    # Opening hours
    hours_obj = place.get("currentOpeningHours") or place.get("regularOpeningHours")
    hours_text = None
    if hours_obj and "weekdayDescriptions" in hours_obj:
        hours_text = "; ".join(hours_obj["weekdayDescriptions"])

    # Reviews
    reviews_raw = place.get("reviews", [])
    review_texts = []
    for r in reviews_raw:
        original = r.get("originalText") or r.get("text")
        if original:
            text = original.get("text", "") if isinstance(original, dict) else str(original)
            if text:
                review_texts.append(text)

    return {
        "place_id": place.get("id"),
        "name": name,
        "address": place.get("formattedAddress"),
        "lat": location.get("latitude"),
        "lng": location.get("longitude"),
        "types": place.get("types", []),
        "rating": place.get("rating"),
        "review_count": place.get("userRatingCount"),
        "phone": place.get("nationalPhoneNumber"),
        "website": place.get("websiteUri"),
        "hours": hours_text,
        "review_texts": review_texts,
    }
