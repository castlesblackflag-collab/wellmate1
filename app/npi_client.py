"""NPPES NPI Registry client: query and parse physician records.

The NPPES API is free, public, and requires no API key.
Rate limits are generous but we still apply timeouts and limit calls.
"""

from __future__ import annotations

from typing import Any

import structlog
from httpx import AsyncClient, TimeoutException

from app.config_loader import cfg

logger = structlog.get_logger()

_NPI_SEARCH_URL = "https://npiregistry.cms.hhs.gov/api/"


def _parse_npi_result(result: dict[str, Any]) -> dict[str, Any]:
    """Extract relevant fields from a single NPI registry result."""
    basic = result.get("basic", {})
    taxonomies = result.get("taxonomies", [])
    addresses = result.get("addresses", [])

    # Get primary practice address
    practice_addr = ""
    practice_city = ""
    practice_state = ""
    practice_zip = ""
    for addr in addresses:
        if addr.get("address_purpose") == "LOCATION":
            practice_addr = addr.get("address_1", "")
            practice_city = addr.get("city", "")
            practice_state = addr.get("state", "")
            practice_zip = addr.get("postal_code", "")[:5]
            break

    # Get credentials and specialties from taxonomies
    credentials: list[str] = []
    specialties: list[str] = []
    for tax in taxonomies:
        desc = tax.get("desc", "")
        if desc and desc not in specialties:
            specialties.append(desc)
        license_str = tax.get("license", "")
        if license_str and license_str not in credentials:
            credentials.append(license_str)

    # Credential from basic info (MD, DO, NP, etc.)
    credential = basic.get("credential", "")
    if credential:
        # Clean up credential string (often has periods and spaces)
        cred_clean = credential.replace(".", "").strip().upper()
        if cred_clean and cred_clean not in credentials:
            credentials.insert(0, cred_clean)

    first_name = basic.get("first_name", "")
    last_name = basic.get("last_name", "")
    org_name = basic.get("organization_name", "")

    return {
        "npi": result.get("number", ""),
        "first_name": first_name,
        "last_name": last_name,
        "organization_name": org_name,
        "full_name": f"{first_name} {last_name}".strip() or org_name,
        "credentials": credentials,
        "specialties": specialties,
        "practice_address": practice_addr,
        "practice_city": practice_city,
        "practice_state": practice_state,
        "practice_zip": practice_zip,
    }


async def search_npi(
    name: str,
    state: str | None,
    city: str | None,
    client: AsyncClient,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search NPI registry by provider name and optional location.

    Searches for individual providers (entity type 1) and organizations (entity type 2).
    Returns parsed NPI records.
    """
    # Split name for individual search
    name_parts = name.strip().split()
    params: dict[str, Any] = {
        "version": "2.1",
        "limit": limit,
    }

    # Try individual provider first (more common for physicians)
    if len(name_parts) >= 2:
        params["first_name"] = name_parts[0]
        params["last_name"] = name_parts[-1]
    else:
        # Single word: try as last name or organization
        params["organization_name"] = name

    if state:
        params["state"] = state
    if city:
        params["city"] = city

    try:
        resp = await client.get(
            _NPI_SEARCH_URL,
            params=params,
            timeout=cfg.upstream_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except (TimeoutException, Exception) as exc:
        logger.error("npi_search_failed", name=name, error=str(exc))
        return []

    results = data.get("results", [])
    if not results:
        # Try organization search if individual search returned nothing
        if "first_name" in params:
            org_params = {
                "version": "2.1",
                "organization_name": name,
                "limit": limit,
            }
            if state:
                org_params["state"] = state
            try:
                resp = await client.get(
                    _NPI_SEARCH_URL,
                    params=org_params,
                    timeout=cfg.upstream_timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
            except (TimeoutException, Exception):
                pass

    parsed = [_parse_npi_result(r) for r in results]
    logger.info("npi_search_ok", name=name, count=len(parsed))
    return parsed
