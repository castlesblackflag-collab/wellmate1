"""
Geography utilities: ZIP code to lat/lng, distance calculations.
"""

import logging
import math
import os

import httpx

logger = logging.getLogger(__name__)

# US ZIP code centroid lookup via free zippopotam.us API
_ZIP_API_URL = "https://api.zippopotam.us/us/{zip_code}"

# Google Geocoding API fallback (uses same PLACES_API_KEY)
_GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def zip_to_latlng(zip_code: str) -> tuple[float, float] | None:
    """Convert a US ZIP code to (latitude, longitude).

    Tries zippopotam.us first, falls back to Google Geocoding API.
    Returns None if all lookups fail.
    """
    code = zip_code.strip()

    # Try zippopotam.us first
    result = _zip_via_zippopotam(code)
    if result:
        return result

    # Fallback: Google Geocoding API (uses PLACES_API_KEY)
    result = _zip_via_google_geocoding(code)
    if result:
        return result

    logger.error("All geocoding methods failed for ZIP %s", code)
    return None


def _zip_via_zippopotam(zip_code: str) -> tuple[float, float] | None:
    url = _ZIP_API_URL.format(zip_code=zip_code)
    try:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        places = data.get("places", [])
        if not places:
            return None
        lat = float(places[0]["latitude"])
        lng = float(places[0]["longitude"])
        return (lat, lng)
    except Exception:
        logger.debug("zippopotam.us lookup failed for ZIP %s, trying fallback", zip_code)
        return None


def _zip_via_google_geocoding(zip_code: str) -> tuple[float, float] | None:
    api_key = os.environ.get("PLACES_API_KEY", "")
    if not api_key:
        return None
    try:
        resp = httpx.get(
            _GOOGLE_GEOCODE_URL,
            params={"address": zip_code, "components": "country:US", "key": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            logger.warning("Google Geocoding returned no results for ZIP %s", zip_code)
            return None
        location = results[0]["geometry"]["location"]
        return (location["lat"], location["lng"])
    except Exception:
        logger.exception("Google Geocoding failed for ZIP %s", zip_code)
        return None


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate the great-circle distance between two points in miles."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c
