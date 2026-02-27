"""Google Places integration: candidate retrieval and enrichment.

Strategy decisions (addressing open questions #2 and #3):

Query strategy:
- Use Places Text Search (new) API rather than Nearby Search. Text Search accepts
  free-text queries like "acupuncturist near Austin TX" and is better suited to
  modality-based searches. Nearby Search is limited to type-based filtering which
  does not cover whole-health categories well.
- Build 1-4 queries per request depending on care_style and mapped modalities.
  Cap at max_search_queries from config.

Cost control:
- Text Search: each call returns up to 20 results. We only need a handful per query.
- Place Details: called only for top-N candidates (max_place_detail_calls from config,
  default 10). We request only the fields we need (formatted_address, phone, website,
  types, rating, user_ratings_total) to minimize per-call cost.
- In-memory cache on Place Details (TTL 1h) prevents repeated enrichment for the same
  place across near-identical searches.
"""

from __future__ import annotations

import math
from typing import Any

import structlog
from cachetools import TTLCache
from httpx import AsyncClient, TimeoutException

from app.config_loader import cfg

logger = structlog.get_logger()

# Cache for Place Details responses keyed by place_id
_details_cache: TTLCache[str, dict] = TTLCache(
    maxsize=1024,
    ttl=cfg.places_cache_ttl,
)

_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

# Fields requested from Place Details (controls billing)
_DETAIL_FIELDS = [
    "id",
    "displayName",
    "formattedAddress",
    "nationalPhoneNumber",
    "websiteUri",
    "types",
    "rating",
    "userRatingCount",
    "location",
]

# Provider type classification based on Places types
_MEDICAL_TYPES = {"doctor", "hospital", "health", "physiotherapist", "dentist"}
_WHOLE_HEALTH_TYPES = {
    "spa", "gym", "yoga_studio", "wellness_center",
}


def _build_search_queries(
    care_style: str,
    goal_outcomes: list[str],
    main_issue: str | None,
    mappings: dict,
    category_queries: dict,
) -> list[str]:
    """Build Places text search query strings from user inputs and config maps.

    Returns a list of query strings, capped at max_search_queries.
    """
    queries: list[str] = []

    # Determine which categories are relevant based on care_style and outcomes
    medical_modalities: set[str] = set()
    wh_modalities: set[str] = set()

    outcome_text = " ".join(goal_outcomes).lower()
    if main_issue:
        outcome_text += " " + main_issue.lower()

    for keyword, modal_map in mappings.items():
        if keyword in outcome_text:
            if care_style in ("medical", "mixed"):
                medical_modalities.update(modal_map.get("medical", []))
            if care_style in ("whole_health", "mixed"):
                wh_modalities.update(modal_map.get("whole_health", []))

    # Build medical queries
    if care_style in ("medical", "mixed"):
        if medical_modalities:
            # Use most specific specialties as query terms
            specs = list(medical_modalities)[:3]
            queries.append(f"{' '.join(specs)} doctor")
        else:
            queries.append("doctor clinic")

    # Build whole-health queries
    if care_style in ("whole_health", "mixed"):
        # Group by modality category and use category_queries
        wh_categories_used: set[str] = set()
        for modality in wh_modalities:
            if modality in category_queries and modality not in wh_categories_used:
                queries.append(category_queries[modality][0])
                wh_categories_used.add(modality)

        # Fallback: if no specific modalities matched, search broadly
        if not wh_categories_used:
            queries.append("wellness holistic health")

    # If nothing was derived, use a broad fallback
    if not queries:
        queries.append("healthcare provider")

    return queries[: cfg.max_search_queries]


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance between two points in kilometers."""
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def classify_provider(types: list[str], query_used: str) -> tuple[str, bool]:
    """Classify a Places result into a provider_category and is_physician flag.

    Returns (category, is_physician).
    """
    types_set = {t.lower() for t in types}
    query_lower = query_used.lower()

    # Check for explicit whole-health categories first
    if "acupuncture" in query_lower or "acupuncturist" in query_lower:
        return "acupuncture", False
    if "yoga" in query_lower:
        return "yoga", False
    if "meditation" in query_lower or "mindfulness" in query_lower:
        return "meditation", False
    if "massage" in query_lower:
        return "massage", False
    if "nutrition" in query_lower or "dietitian" in query_lower:
        return "nutrition", False
    if "counselor" in query_lower or "therapist mental" in query_lower:
        return "counseling", False
    if "chiropract" in query_lower:
        return "chiropractic", False
    if "physical therap" in query_lower:
        return "physical_therapy", False

    # Check Places types
    if types_set & _MEDICAL_TYPES:
        if "hospital" in types_set or "health" in types_set:
            return "clinic", True
        return "physician", True

    # Fallback based on query
    if "doctor" in query_lower or "physician" in query_lower or "clinic" in query_lower:
        return "physician", True

    if types_set & _WHOLE_HEALTH_TYPES:
        return "other", False

    return "other", False


async def search_places(
    query: str,
    lat: float,
    lng: float,
    radius_km: int,
    client: AsyncClient,
) -> list[dict[str, Any]]:
    """Execute a Places Text Search and return raw place results."""
    radius_m = radius_km * 1000
    headers = {
        "X-Goog-Api-Key": cfg.places_api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.types,places.rating,places.userRatingCount,"
            "places.location"
        ),
    }
    body = {
        "textQuery": query,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius_m),
            }
        },
        "maxResultCount": 10,
    }

    try:
        resp = await client.post(
            _TEXT_SEARCH_URL,
            json=body,
            headers=headers,
            timeout=cfg.upstream_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except (TimeoutException, Exception) as exc:
        logger.error("places_search_failed", query=query, error=str(exc))
        return []

    places = data.get("places", [])
    logger.info("places_search_ok", query=query, count=len(places))
    return places


async def get_place_details(
    place_id: str,
    client: AsyncClient,
) -> dict[str, Any] | None:
    """Fetch Place Details for a single place. Cached."""
    if place_id in _details_cache:
        return _details_cache[place_id]

    url = _PLACE_DETAILS_URL.format(place_id=place_id)
    field_mask = ",".join(_DETAIL_FIELDS)
    headers = {
        "X-Goog-Api-Key": cfg.places_api_key,
        "X-Goog-FieldMask": field_mask,
    }

    try:
        resp = await client.get(url, headers=headers, timeout=cfg.upstream_timeout)
        resp.raise_for_status()
        data = resp.json()
    except (TimeoutException, Exception) as exc:
        logger.error("place_details_failed", place_id=place_id, error=str(exc))
        return None

    _details_cache[place_id] = data
    return data


def parse_place_to_candidate(
    place: dict[str, Any],
    query_used: str,
    origin_lat: float,
    origin_lng: float,
) -> dict[str, Any]:
    """Convert a raw Places API result into a normalized candidate dict."""
    place_id = place.get("id", "")
    display_name = place.get("displayName", {})
    name = display_name.get("text", "") if isinstance(display_name, dict) else str(display_name)
    address = place.get("formattedAddress", "")
    types = place.get("types", [])
    rating = place.get("rating")
    review_count = place.get("userRatingCount")
    location = place.get("location", {})
    lat = location.get("latitude", 0.0)
    lng = location.get("longitude", 0.0)

    dist = _distance_km(origin_lat, origin_lng, lat, lng) if lat and lng else None

    category, is_physician = classify_provider(types, query_used)

    return {
        "place_id": place_id,
        "name": name,
        "address": address,
        "types": types,
        "rating": rating,
        "review_count": review_count,
        "lat": lat,
        "lng": lng,
        "distance_km": round(dist, 1) if dist is not None else None,
        "category": category,
        "is_physician": is_physician,
        "phone": None,
        "website": None,
        "query_used": query_used,
    }


async def enrich_with_details(
    candidate: dict[str, Any],
    client: AsyncClient,
) -> dict[str, Any]:
    """Enrich a candidate with Place Details (phone, website)."""
    details = await get_place_details(candidate["place_id"], client)
    if details:
        candidate["phone"] = details.get("nationalPhoneNumber")
        candidate["website"] = details.get("websiteUri")
        # Update rating/review if details has them and search didn't
        if candidate["rating"] is None:
            candidate["rating"] = details.get("rating")
        if candidate["review_count"] is None:
            candidate["review_count"] = details.get("userRatingCount")
    return candidate


async def retrieve_candidates(
    care_style: str,
    goal_outcomes: list[str],
    main_issue: str | None,
    lat: float,
    lng: float,
    radius_km: int,
    client: AsyncClient,
) -> list[dict[str, Any]]:
    """Full pipeline: build queries, search, deduplicate, enrich top-N.

    Returns a list of enriched candidate dicts.
    """
    queries = _build_search_queries(
        care_style=care_style,
        goal_outcomes=goal_outcomes,
        main_issue=main_issue,
        mappings=cfg.outcome_to_modalities,
        category_queries=cfg.category_to_places_queries,
    )

    logger.info("places_queries_built", queries=queries, count=len(queries))

    # Execute all search queries
    all_candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for query in queries:
        places = await search_places(query, lat, lng, radius_km, client)
        for place in places:
            pid = place.get("id", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                candidate = parse_place_to_candidate(place, query, lat, lng)
                all_candidates.append(candidate)

    logger.info("places_candidates_total", count=len(all_candidates))

    # Filter out candidates beyond radius
    all_candidates = [
        c for c in all_candidates
        if c["distance_km"] is None or c["distance_km"] <= radius_km
    ]

    # Enrich top-N with Place Details
    detail_limit = min(cfg.max_place_detail_calls, len(all_candidates))
    for i in range(detail_limit):
        all_candidates[i] = await enrich_with_details(all_candidates[i], client)

    return all_candidates
