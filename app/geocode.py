"""Location resolution: location_text -> (lat, lng, formatted_address).

Strategy decision (addressing open question #1):
- Use Google Geocoding API for maximum flexibility (handles ZIP, city, city+state,
  partial addresses, and international input).
- A static ZIP dataset would be cheaper but cannot handle city names, typos, or
  non-US locations. Geocoding API is worth the small per-call cost given we cache
  aggressively.
- Cache in-memory with TTL (default 24h). For multi-instance Cloud Run, each
  instance warms its own cache. A shared cache (Redis/Memorystore) is recommended
  at scale but not required for MVP.
"""

from __future__ import annotations

import structlog
from cachetools import TTLCache
from httpx import AsyncClient, HTTPStatusError, TimeoutException

from app.config_loader import cfg

logger = structlog.get_logger()

GeoResult = tuple[float, float, str]  # (lat, lng, formatted_address)

_cache: TTLCache[str, GeoResult] = TTLCache(
    maxsize=2048,
    ttl=cfg.geocode_cache_ttl,
)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


async def resolve_location(
    location_text: str,
    client: AsyncClient,
) -> GeoResult | None:
    """Resolve free-text location to lat/lng.

    Returns (lat, lng, formatted_address) or None if resolution fails.
    """
    cache_key = location_text.strip().lower()
    if cache_key in _cache:
        logger.info("geocode_cache_hit", location=cache_key)
        return _cache[cache_key]

    try:
        resp = await client.get(
            _GEOCODE_URL,
            params={
                "address": location_text,
                "key": cfg.places_api_key,
            },
            timeout=cfg.upstream_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except (HTTPStatusError, TimeoutException, Exception) as exc:
        logger.error("geocode_failed", location=cache_key, error=str(exc))
        return None

    results = data.get("results", [])
    if not results:
        logger.warning("geocode_no_results", location=cache_key)
        return None

    geo = results[0]["geometry"]["location"]
    address = results[0].get("formatted_address", location_text)
    result: GeoResult = (geo["lat"], geo["lng"], address)

    _cache[cache_key] = result
    logger.info("geocode_resolved", location=cache_key, address=address)
    return result
