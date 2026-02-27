"""Schema validation tests for the tool contract.

Acceptance tests addressed:
- AT1: Tool request with only required fields succeeds.
- AT2: Tool returns strict schema even with missing optional data.
- AT3: Error responses maintain strict schema shape.
- AT4: Partial data does not break response shape.
"""

import pytest
from pydantic import ValidationError

from app.schema import (
    ProviderContact,
    ProviderResult,
    ResponseMeta,
    SearchRequest,
    SearchResponse,
)


class TestSearchRequest:
    """Validate request schema behavior."""

    def test_minimal_required_fields_only(self):
        """AT1: Request with only required fields should parse successfully."""
        req = SearchRequest(
            location_text="78701",
            care_style="medical",
            goal_outcomes=["walk without pain"],
        )
        assert req.location_text == "78701"
        assert req.care_style == "medical"
        assert req.goal_outcomes == ["walk without pain"]

    def test_server_defaults_applied(self):
        """All optional fields should have safe defaults."""
        req = SearchRequest(
            location_text="Austin, TX",
            care_style="mixed",
            goal_outcomes=["reduce stress"],
        )
        assert req.radius_km == 20
        assert req.max_results == 5
        assert req.visit_mode == "either"
        assert req.preferences == []
        assert req.avoidances == []
        assert req.diagnoses == []
        assert req.main_issue is None
        assert req.insurance_hint is None

    def test_all_fields_provided(self):
        """Request with all fields should parse successfully."""
        req = SearchRequest(
            location_text="78701",
            care_style="whole_health",
            goal_outcomes=["reduce pain", "improve sleep"],
            main_issue="chronic back pain",
            diagnoses=["lumbar disc herniation"],
            preferences=["non-pharmacologic", "mind-body"],
            avoidances=["opioids", "surgery"],
            visit_mode="in_person",
            insurance_hint="Blue Cross",
            radius_km=30,
            max_results=10,
        )
        assert req.care_style == "whole_health"
        assert len(req.goal_outcomes) == 2
        assert len(req.preferences) == 2
        assert req.radius_km == 30

    def test_invalid_care_style_rejected(self):
        """Invalid enum value for care_style should be rejected."""
        with pytest.raises(ValidationError):
            SearchRequest(
                location_text="78701",
                care_style="invalid",
                goal_outcomes=["test"],
            )

    def test_invalid_visit_mode_rejected(self):
        """Invalid enum value for visit_mode should be rejected."""
        with pytest.raises(ValidationError):
            SearchRequest(
                location_text="78701",
                care_style="medical",
                goal_outcomes=["test"],
                visit_mode="virtual",
            )

    def test_empty_goal_outcomes_rejected(self):
        """goal_outcomes must have at least 1 item."""
        with pytest.raises(ValidationError):
            SearchRequest(
                location_text="78701",
                care_style="medical",
                goal_outcomes=[],
            )

    def test_missing_location_rejected(self):
        """location_text is required."""
        with pytest.raises(ValidationError):
            SearchRequest(
                care_style="medical",
                goal_outcomes=["test"],
            )

    def test_radius_bounds(self):
        """radius_km must be between 1 and 100."""
        with pytest.raises(ValidationError):
            SearchRequest(
                location_text="78701",
                care_style="medical",
                goal_outcomes=["test"],
                radius_km=0,
            )
        with pytest.raises(ValidationError):
            SearchRequest(
                location_text="78701",
                care_style="medical",
                goal_outcomes=["test"],
                radius_km=200,
            )


class TestSearchResponse:
    """Validate response schema strictness."""

    def test_empty_response_has_all_keys(self):
        """AT2: Even an empty response must have results, meta, warnings, error."""
        resp = SearchResponse(
            results=[],
            meta=ResponseMeta(),
            warnings=[],
            error=None,
        )
        data = resp.model_dump()
        assert "results" in data
        assert "meta" in data
        assert "warnings" in data
        assert "error" in data
        assert data["results"] == []
        assert data["error"] is None

    def test_error_response_has_all_keys(self):
        """AT3: Error response maintains strict shape."""
        resp = SearchResponse(
            results=[],
            meta=ResponseMeta(),
            warnings=["NPI verification temporarily unavailable"],
            error="Could not resolve location: 00000",
        )
        data = resp.model_dump()
        assert data["results"] == []
        assert data["error"] == "Could not resolve location: 00000"
        assert len(data["warnings"]) == 1
        assert "meta" in data

    def test_response_with_results(self):
        """Response with provider results serializes correctly."""
        result = ProviderResult(
            provider_id="ChIJ_test_123",
            name="Austin Pain Clinic",
            provider_category="physician",
            is_physician=True,
            npi_verified=True,
            credentials=["MD"],
            specialties=["Pain Medicine"],
            address="123 Main St, Austin, TX 78701",
            distance_km=4.2,
            rating=4.7,
            review_count=86,
            visit_modes=["in_person"],
            contact=ProviderContact(phone="512-555-0100", website="https://example.com"),
            score=91,
            fit_reasons=[
                "Matches goal: improve mobility",
                "Aligns with preference: non-pharmacologic care",
            ],
            data_sources=["google_places", "npi_registry"],
        )
        resp = SearchResponse(
            results=[result],
            meta=ResponseMeta(
                location_resolved="Austin, TX",
                lat=30.2672,
                lng=-97.7431,
                radius_km=20,
                result_count=1,
                care_style="medical",
                goal_outcomes=["improve mobility"],
            ),
            warnings=[],
            error=None,
        )
        data = resp.model_dump()
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "Austin Pain Clinic"
        assert data["results"][0]["score"] == 91
        assert data["meta"]["result_count"] == 1

    def test_provider_with_null_optional_fields(self):
        """AT4: Provider with missing optional data serializes without error."""
        result = ProviderResult(
            provider_id="test_id",
            name="Unknown Clinic",
            provider_category="other",
            score=40,
            # All other fields use defaults (None, empty lists, False)
        )
        data = result.model_dump()
        assert data["address"] is None
        assert data["distance_km"] is None
        assert data["rating"] is None
        assert data["review_count"] is None
        assert data["contact"]["phone"] is None
        assert data["contact"]["website"] is None
        assert data["is_physician"] is False
        assert data["npi_verified"] is False

    def test_response_meta_defaults(self):
        """ResponseMeta with no arguments should have safe defaults."""
        meta = ResponseMeta()
        data = meta.model_dump()
        assert data["location_resolved"] is None
        assert data["lat"] is None
        assert data["lng"] is None
        assert data["radius_km"] == 20
        assert data["result_count"] == 0

    def test_score_bounds_enforced(self):
        """Score must be between 0 and 100."""
        with pytest.raises(ValidationError):
            ProviderResult(
                provider_id="test",
                name="Test",
                provider_category="physician",
                score=101,
            )
        with pytest.raises(ValidationError):
            ProviderResult(
                provider_id="test",
                name="Test",
                provider_category="physician",
                score=-1,
            )
