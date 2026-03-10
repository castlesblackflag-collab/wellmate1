"""
Geography utilities: ZIP code to lat/lng, distance calculations.
"""

import logging
import math

import httpx

logger = logging.getLogger(__name__)

# US ZIP code centroid lookup via free zippopotam.us API
_ZIP_API_URL = "https://api.zippopotam.us/us/{zip_code}"


def zip_to_latlng(zip_code: str) -> tuple[float, float] | None:
    """Convert a US ZIP code to (latitude, longitude).

    Returns None if the lookup fails.
    """
    url = _ZIP_API_URL.format(zip_code=zip_code.strip())
    try:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        places = data.get("places", [])
        if not places:
            logger.warning("No places found for ZIP %s", zip_code)
            return None
        lat = float(places[0]["latitude"])
        lng = float(places[0]["longitude"])
        return (lat, lng)
    except Exception:
        logger.exception("Failed to geocode ZIP %s", zip_code)
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
