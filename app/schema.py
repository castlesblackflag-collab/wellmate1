"""Pydantic request/response models for the search_practitioners tool contract.

Design principles (Playbook-first):
- Minimal required fields: location_text, care_style, goal_outcomes
- Flat request body, no deep nesting
- Server-side defaults for all optional fields
- Strict response shape: results/meta/warnings/error always present
- Backend returns facts only, no prose
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    """Flat, LLM-friendly request schema for search_practitioners."""

    # --- Required (Playbook must always provide these) ---
    location_text: str = Field(
        ...,
        description="ZIP code or city name, e.g. '78701' or 'Austin, TX'",
    )
    care_style: Literal["medical", "whole_health", "mixed"] = Field(
        ...,
        description="Type of care sought: medical, whole_health, or mixed",
    )
    goal_outcomes: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="1-5 short outcome strings the user wants to achieve",
    )

    # --- Optional (server provides safe defaults) ---
    main_issue: str | None = Field(
        default=None,
        description="Primary symptom or issue, e.g. 'chronic lower back pain'",
    )
    diagnoses: list[str] = Field(
        default_factory=list,
        description="Known diagnoses, e.g. ['type 2 diabetes']",
    )
    preferences: list[str] = Field(
        default_factory=list,
        description="Care preferences, e.g. ['non-pharmacologic', 'mind-body']",
    )
    avoidances: list[str] = Field(
        default_factory=list,
        description="Things to avoid, e.g. ['opioids', 'surgery']",
    )
    visit_mode: Literal["in_person", "telehealth", "either"] = Field(
        default="either",
        description="Preferred visit modality",
    )
    insurance_hint: str | None = Field(
        default=None,
        description="Insurance carrier hint (informational only)",
    )
    radius_km: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Search radius in kilometers",
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of results to return",
    )


# ---------------------------------------------------------------------------
# Response sub-models
# ---------------------------------------------------------------------------

class ProviderContact(BaseModel):
    """Contact information. Null fields mean data was unavailable."""
    phone: str | None = None
    website: str | None = None


class ProviderResult(BaseModel):
    """A single provider in the results list."""
    provider_id: str = Field(description="Stable identifier (place_id or hash)")
    name: str
    provider_category: Literal[
        "physician", "clinic", "acupuncture", "yoga",
        "meditation", "massage", "nutrition", "counseling",
        "chiropractic", "physical_therapy", "other",
    ]
    is_physician: bool = False
    npi_verified: bool = False
    credentials: list[str] = Field(default_factory=list)
    specialties: list[str] = Field(default_factory=list)
    address: str | None = None
    distance_km: float | None = None
    rating: float | None = None
    review_count: int | None = None
    visit_modes: list[str] = Field(default_factory=list)
    contact: ProviderContact = Field(default_factory=ProviderContact)
    score: int = Field(ge=0, le=100, description="Composite fit score 0-100")
    fit_reasons: list[str] = Field(
        default_factory=list,
        description="2-5 short reason strings tied to user goals",
    )
    data_sources: list[str] = Field(default_factory=list)


class ResponseMeta(BaseModel):
    """Metadata about the search execution."""
    location_resolved: str | None = None
    lat: float | None = None
    lng: float | None = None
    radius_km: int = 20
    result_count: int = 0
    care_style: str = ""
    goal_outcomes: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """Strict response shape. Always the same keys, even on error or empty."""
    results: list[ProviderResult] = Field(default_factory=list)
    meta: ResponseMeta = Field(default_factory=ResponseMeta)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
