"""Tests for weighted scoring logic."""

from practitioner_finder_poc.services.scoring import (
    score_practitioner,
    _score_type_match,
    _score_proximity,
    _score_rating,
    _score_accessibility,
    _score_preference_alignment,
    _score_outcome_alignment,
)


def _make_provider(**overrides):
    base = {
        "place_id": "test_001",
        "name": "Test Physical Therapy Clinic",
        "address": "123 Main St, Austin, TX 78701",
        "lat": 30.27,
        "lng": -97.74,
        "types": ["physiotherapist", "health", "establishment"],
        "rating": 4.5,
        "review_count": 50,
        "phone": "(512) 555-0001",
        "website": "https://example.com",
        "hours": "Mon-Fri: 9-5",
        "review_texts": ["Great clinic for pain relief and rehab."],
    }
    base.update(overrides)
    return base


class TestTypeMatch:
    def test_matching_type_in_name(self):
        provider = _make_provider(name="Downtown Physical Therapy")
        score = _score_type_match(provider, ["physical therapist"])
        assert score >= 0.7

    def test_no_match(self):
        provider = _make_provider(name="Coffee Shop", types=["cafe"])
        score = _score_type_match(provider, ["gastroenterologist"])
        assert score < 0.5

    def test_empty_types_returns_neutral(self):
        provider = _make_provider()
        score = _score_type_match(provider, [])
        assert score == 0.5


class TestProximity:
    def test_same_location_scores_high(self):
        provider = _make_provider(lat=30.27, lng=-97.74)
        score = _score_proximity(provider, 30.27, -97.74, 10)
        assert score > 0.9

    def test_far_location_scores_low(self):
        provider = _make_provider(lat=31.0, lng=-97.0)
        score = _score_proximity(provider, 30.27, -97.74, 10)
        assert score < 0.2

    def test_missing_coords_returns_low(self):
        provider = _make_provider(lat=None, lng=None)
        score = _score_proximity(provider, 30.27, -97.74, 10)
        assert score == 0.3


class TestRating:
    def test_high_rating_many_reviews(self):
        provider = _make_provider(rating=4.8, review_count=100)
        score = _score_rating(provider)
        assert score > 0.8

    def test_no_rating(self):
        provider = _make_provider(rating=None, review_count=0)
        score = _score_rating(provider)
        assert score == 0.3

    def test_low_rating(self):
        provider = _make_provider(rating=2.0, review_count=10)
        score = _score_rating(provider)
        assert score < 0.5


class TestAccessibility:
    def test_all_prefs_met(self):
        provider = _make_provider(phone="555-1234", website="https://example.com", hours="Mon-Fri: 9-5")
        prefs = ["phone number listed", "website listed", "hours of operation listed"]
        score = _score_accessibility(provider, prefs)
        assert score == 1.0

    def test_no_prefs_met(self):
        provider = _make_provider(phone=None, website=None, hours=None)
        prefs = ["phone number listed", "website listed"]
        score = _score_accessibility(provider, prefs)
        assert score == 0.0

    def test_empty_prefs_returns_neutral(self):
        provider = _make_provider()
        score = _score_accessibility(provider, [])
        assert score == 0.5


class TestPreferenceAlignment:
    def test_aligned(self):
        score = _score_preference_alignment(
            ["physical therapist", "acupuncturist"], ["non-pharmacologic"]
        )
        assert score > 0.5

    def test_not_aligned(self):
        score = _score_preference_alignment(
            ["general practitioner"], ["naturopathic"]
        )
        assert score < 0.5

    def test_empty(self):
        score = _score_preference_alignment([], [])
        assert score == 0.5


class TestOutcomeAlignment:
    def test_walking_without_pain(self):
        score = _score_outcome_alignment(
            ["physical therapist"], ["walking without pain"]
        )
        assert score > 0.5

    def test_no_alignment(self):
        score = _score_outcome_alignment(
            ["massage therapist"], ["improving digestion"]
        )
        assert score < 0.5

    def test_empty_outcomes(self):
        score = _score_outcome_alignment(["physical therapist"], [])
        assert score == 0.5


class TestFullScoring:
    def test_returns_required_fields(self):
        provider = _make_provider()
        result = score_practitioner(
            provider=provider,
            center_lat=30.27,
            center_lng=-97.74,
            radius_miles=10,
            practitioner_types=["physical therapist"],
            symptoms=["pain"],
            accessibility_prefs=["phone number listed"],
            preference_weights=["non-pharmacologic"],
            preferred_outcomes=["walking without pain"],
            npi_result={"confidence": 0.5},
        )
        assert "total_score" in result
        assert "breakdown" in result
        assert "blurb" in result
        assert isinstance(result["total_score"], float)
        assert 0 <= result["total_score"] <= 100

    def test_score_is_deterministic(self):
        provider = _make_provider()
        kwargs = dict(
            provider=provider,
            center_lat=30.27,
            center_lng=-97.74,
            radius_miles=10,
            practitioner_types=["physical therapist"],
            symptoms=["pain"],
            accessibility_prefs=[],
            preference_weights=[],
            preferred_outcomes=[],
            npi_result={"confidence": 0.0},
        )
        r1 = score_practitioner(**kwargs)
        r2 = score_practitioner(**kwargs)
        assert r1["total_score"] == r2["total_score"]
