"""FastAPI application: single POST /search_practitioners endpoint.

This is the Cloud Run entry point. It orchestrates the full pipeline:
  geocode -> places search -> NPI enrichment -> scoring -> strict response.

Error handling strategy:
- All exceptions are caught and returned in the strict response shape.
- Upstream failures degrade gracefully (partial results + warnings).
- No stack traces or unstructured errors ever reach the client.

Observability:
- Structured JSON logs via structlog (compatible with Cloud Logging).
- Logs: request_id, latency, upstream status, result counts.
- Does NOT log raw user free text (goal_outcomes, main_issue).

Schema design:
- Uses Literal types for enums (not free strings) so the LLM picks
  from a closed set.
- Only 2 required fields (location_text, provider_scope); everything else
  has safe defaults.
- Response shape never varies; even errors return the full structure.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import AsyncClient

from app.config_loader import cfg
from app.geocode import resolve_location
from app.matcher import enrich_candidates_with_npi
from app.places_client import retrieve_candidates
from app.schema import (
    ProviderContact,
    ProviderResult,
    ResponseMeta,
    SearchRequest,
    SearchResponse,
)
from app.scoring import score_and_rank_candidates

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger()

# Shared HTTP client for upstream API calls
_http_client: AsyncClient | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global _http_client
    _http_client = AsyncClient()
    logger.info("app_started", version="0.2.0")
    yield
    await _http_client.aclose()
    logger.info("app_stopped")


app = FastAPI(
    title="Wellmate Practitioner Finder",
    description=(
        "Search and rank healthcare practitioners based on user goals, "
        "provider scope, and location. Designed for Google "
        "Conversational Agent / Playbook tool integration."
    ),
    version="0.2.0",
    lifespan=lifespan,
)


def _check_urgent_symptoms(
    goal_outcomes: list[str],
    main_issue: str | None,
) -> list[str]:
    """Check for urgent symptom patterns and return safety warnings."""
    warnings: list[str] = []
    text = " ".join(goal_outcomes).lower()
    if main_issue:
        text += " " + main_issue.lower()

    for pattern in cfg.urgent_symptoms:
        if pattern.lower() in text:
            warnings.append(
                "SAFETY: If you are experiencing a medical emergency, "
                "please call 911 or go to the nearest emergency room."
            )
            break
    return warnings


def _build_provider_result(candidate: dict) -> ProviderResult:
    """Convert an internal candidate dict to the strict ProviderResult schema."""
    data_sources = ["google_places"]
    if candidate.get("npi_verified"):
        data_sources.append("npi_registry")

    # Merge NPI specialties with query-derived category
    specialties = list(candidate.get("npi_specialties", []))

    # Determine visit_modes (best-effort; Places does not reliably provide this)
    visit_modes = ["in_person"]

    return ProviderResult(
        provider_id=candidate.get("place_id", ""),
        name=candidate.get("name", ""),
        provider_category=candidate.get("category", "other"),
        is_physician=candidate.get("is_physician", False),
        npi_verified=candidate.get("npi_verified", False),
        credentials=candidate.get("credentials", []),
        specialties=specialties,
        address=candidate.get("address"),
        distance_km=candidate.get("distance_km"),
        rating=candidate.get("rating"),
        review_count=candidate.get("review_count"),
        visit_modes=visit_modes,
        contact=ProviderContact(
            phone=candidate.get("phone"),
            website=candidate.get("website"),
        ),
        score=candidate.get("score", 0),
        fit_reasons=candidate.get("fit_reasons", []),
        data_sources=data_sources,
    )


def _error_response(error_msg: str, warnings: list[str] | None = None) -> SearchResponse:
    """Build a strict-shape error response."""
    return SearchResponse(
        results=[],
        meta=ResponseMeta(),
        warnings=warnings or [],
        error=error_msg,
    )


@app.get("/")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "wellmate-practitioner-finder", "version": "0.2.0"}


@app.post(
    "/search_practitioners",
    response_model=SearchResponse,
    summary="Search and rank practitioners by user goals and preferences",
    description=(
        "Primary tool endpoint for the Practitioner Finder Playbook. "
        "Accepts provider scope, optional goals, and location; returns ranked "
        "providers with structured fit reasons."
    ),
)
async def search_practitioners(req: SearchRequest) -> SearchResponse:
    """Main search endpoint. Orchestrates the full pipeline."""
    request_id = uuid.uuid4().hex[:12]
    start_time = time.monotonic()
    warnings: list[str] = []

    logger.info(
        "search_started",
        request_id=request_id,
        provider_scope=req.provider_scope,
        outcome_count=len(req.goal_outcomes),
        radius_km=req.radius_km,
    )

    # Safety check
    warnings.extend(_check_urgent_symptoms(req.goal_outcomes, req.main_issue))

    # Step 1: Resolve location
    client = _http_client
    if client is None:
        return _error_response("Service not initialized", warnings)

    geo = await resolve_location(req.location_text, client)
    if geo is None:
        logger.warning("search_location_failed", request_id=request_id)
        return _error_response(
            f"Could not resolve location: {req.location_text}",
            warnings,
        )

    lat, lng, resolved_address = geo

    # Step 2: Retrieve candidates from Google Places
    try:
        candidates = await retrieve_candidates(
            provider_scope=req.provider_scope,
            goal_outcomes=req.goal_outcomes,
            main_issue=req.main_issue,
            lat=lat,
            lng=lng,
            radius_km=req.radius_km,
            client=client,
        )
    except Exception as exc:
        logger.error("search_places_failed", request_id=request_id, error=str(exc))
        return _error_response("Provider search failed", warnings)

    if not candidates:
        logger.info("search_no_candidates", request_id=request_id)
        return SearchResponse(
            results=[],
            meta=ResponseMeta(
                location_resolved=resolved_address,
                lat=lat,
                lng=lng,
                radius_km=req.radius_km,
                result_count=0,
                provider_scope=req.provider_scope,
                goal_outcomes=req.goal_outcomes,
            ),
            warnings=warnings + [f"No providers found within {req.radius_km} km"],
            error=None,
        )

    # Step 3: NPI enrichment (graceful degradation)
    try:
        candidates, npi_available = await enrich_candidates_with_npi(candidates, client)
        if not npi_available:
            warnings.append("NPI verification temporarily unavailable")
    except Exception as exc:
        logger.error("search_npi_failed", request_id=request_id, error=str(exc))
        warnings.append("NPI verification temporarily unavailable")

    # Step 4: Score and rank
    ranked = score_and_rank_candidates(
        candidates=candidates,
        goal_outcomes=req.goal_outcomes,
        main_issue=req.main_issue,
        provider_scope=req.provider_scope,
        preferences=req.preferences,
        avoidances=req.avoidances,
        visit_mode=req.visit_mode,
        radius_km=req.radius_km,
        max_results=req.max_results,
    )

    # Step 5: Build strict response
    results = [_build_provider_result(c) for c in ranked]

    elapsed = time.monotonic() - start_time
    logger.info(
        "search_completed",
        request_id=request_id,
        candidates_found=len(candidates),
        results_returned=len(results),
        latency_ms=round(elapsed * 1000),
    )

    return SearchResponse(
        results=results,
        meta=ResponseMeta(
            location_resolved=resolved_address,
            lat=lat,
            lng=lng,
            radius_km=req.radius_km,
            result_count=len(results),
            provider_scope=req.provider_scope,
            goal_outcomes=req.goal_outcomes,
        ),
        warnings=warnings,
        error=None,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: never return raw exceptions. Always return strict shape."""
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    response = _error_response("Internal server error")
    return JSONResponse(
        status_code=200,  # Return 200 so Playbook processes the error field
        content=response.model_dump(),
    )
