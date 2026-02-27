"""Unit tests for the deterministic scoring engine.

Acceptance tests addressed:
- AT6: Fit reasons tie back to goal outcomes and preferences.
- Scoring determinism: same inputs always produce same outputs.
- Outcome-first ranking: results differ from naive popularity ordering.
"""

from app.scoring import (
    generate_fit_reasons,
    score_and_rank_candidates,
    score_candidate,
)


def _make_candidate(**overrides):
    """Build a minimal candidate dict with sensible defaults."""
    base = {
        "place_id": "test_place_1",
        "name": "Test Provider",
        "address": "123 Main St, Austin, TX 78701",
        "types": ["doctor"],
        "rating": 4.5,
        "review_count": 50,
        "lat": 30.27,
        "lng": -97.74,
        "distance_km": 5.0,
        "category": "physician",
        "is_physician": True,
        "phone": None,
        "website": None,
        "query_used": "doctor",
        "npi_verified": False,
        "credentials": [],
        "npi_specialties": [],
    }
    base.update(overrides)
    return base


class TestScoreCandidate:
    """Tests for individual candidate scoring."""

    def test_deterministic_same_inputs(self):
        """Same inputs always produce the same score."""
        candidate = _make_candidate()
        kwargs = dict(
            goal_outcomes=["reduce pain"],
            main_issue="back pain",
            diagnoses=[],
            care_style="medical",
            preferences=[],
            avoidances=[],
            visit_mode="either",
            radius_km=20,
        )
        score1, _ = score_candidate(candidate=candidate, **kwargs)
        score2, _ = score_candidate(candidate=candidate, **kwargs)
        assert score1 == score2

    def test_score_in_valid_range(self):
        """Score must be between 0 and 100."""
        candidate = _make_candidate()
        score, _ = score_candidate(
            candidate=candidate,
            goal_outcomes=["improve mobility"],
            main_issue=None,
            diagnoses=[],
            care_style="medical",
            preferences=[],
            avoidances=[],
            visit_mode="either",
            radius_km=20,
        )
        assert 0 <= score <= 100

    def test_care_style_alignment_medical(self):
        """A physician should score higher for medical care_style than whole_health."""
        physician = _make_candidate(category="physician", is_physician=True)

        score_med, subs_med = score_candidate(
            candidate=physician,
            goal_outcomes=["get treatment"],
            main_issue=None,
            diagnoses=[],
            care_style="medical",
            preferences=[],
            avoidances=[],
            visit_mode="either",
            radius_km=20,
        )
        score_wh, subs_wh = score_candidate(
            candidate=physician,
            goal_outcomes=["get treatment"],
            main_issue=None,
            diagnoses=[],
            care_style="whole_health",
            preferences=[],
            avoidances=[],
            visit_mode="either",
            radius_km=20,
        )
        assert subs_med["care_style_alignment"] > subs_wh["care_style_alignment"]

    def test_care_style_alignment_whole_health(self):
        """A yoga provider should score higher for whole_health care_style."""
        yoga = _make_candidate(category="yoga", is_physician=False)

        _, subs_wh = score_candidate(
            candidate=yoga,
            goal_outcomes=["reduce stress"],
            main_issue=None,
            diagnoses=[],
            care_style="whole_health",
            preferences=[],
            avoidances=[],
            visit_mode="either",
            radius_km=20,
        )
        _, subs_med = score_candidate(
            candidate=yoga,
            goal_outcomes=["reduce stress"],
            main_issue=None,
            diagnoses=[],
            care_style="medical",
            preferences=[],
            avoidances=[],
            visit_mode="either",
            radius_km=20,
        )
        assert subs_wh["care_style_alignment"] > subs_med["care_style_alignment"]

    def test_closer_provider_scores_higher_accessibility(self):
        """A provider at 2km should have better accessibility than one at 18km."""
        close = _make_candidate(distance_km=2.0)
        far = _make_candidate(distance_km=18.0)

        _, subs_close = score_candidate(
            candidate=close,
            goal_outcomes=["get care"],
            main_issue=None,
            diagnoses=[],
            care_style="medical",
            preferences=[],
            avoidances=[],
            visit_mode="either",
            radius_km=20,
        )
        _, subs_far = score_candidate(
            candidate=far,
            goal_outcomes=["get care"],
            main_issue=None,
            diagnoses=[],
            care_style="medical",
            preferences=[],
            avoidances=[],
            visit_mode="either",
            radius_km=20,
        )
        assert subs_close["accessibility"] > subs_far["accessibility"]

    def test_preference_boosts_matching_category(self):
        """Non-pharmacologic preference should boost acupuncture provider."""
        acupuncture = _make_candidate(category="acupuncture", is_physician=False)

        _, subs_pref = score_candidate(
            candidate=acupuncture,
            goal_outcomes=["reduce pain"],
            main_issue=None,
            diagnoses=[],
            care_style="whole_health",
            preferences=["non-pharmacologic"],
            avoidances=[],
            visit_mode="either",
            radius_km=20,
        )
        _, subs_no_pref = score_candidate(
            candidate=acupuncture,
            goal_outcomes=["reduce pain"],
            main_issue=None,
            diagnoses=[],
            care_style="whole_health",
            preferences=[],
            avoidances=[],
            visit_mode="either",
            radius_km=20,
        )
        assert subs_pref["preference_alignment"] > subs_no_pref["preference_alignment"]

    def test_review_quality_with_no_rating(self):
        """Provider with no rating data should get below-average review score."""
        no_rating = _make_candidate(rating=None, review_count=None)
        _, subs = score_candidate(
            candidate=no_rating,
            goal_outcomes=["get care"],
            main_issue=None,
            diagnoses=[],
            care_style="medical",
            preferences=[],
            avoidances=[],
            visit_mode="either",
            radius_km=20,
        )
        assert subs["review_quality"] < 50.0


class TestOutcomeFirstRanking:
    """Verify that outcome alignment drives ranking, not popularity alone."""

    def test_outcome_aligned_beats_popular(self):
        """A pain specialist should rank above a popular general provider
        when the user goal is pain-related."""
        # Specialist: lower rating but matches pain outcomes
        specialist = _make_candidate(
            place_id="specialist",
            name="Pain Specialist",
            category="physician",
            rating=4.0,
            review_count=30,
            query_used="Pain Medicine doctor",
            npi_specialties=["Pain Medicine"],
        )
        # Popular: higher rating but no specialty match
        popular = _make_candidate(
            place_id="popular",
            name="Popular Clinic",
            category="clinic",
            rating=4.9,
            review_count=500,
            query_used="doctor clinic",
            npi_specialties=[],
        )

        ranked = score_and_rank_candidates(
            candidates=[popular, specialist],
            goal_outcomes=["walk without pain", "avoid long-term meds"],
            main_issue="chronic back pain",
            diagnoses=[],
            care_style="medical",
            preferences=["non-pharmacologic"],
            avoidances=["opioids"],
            visit_mode="either",
            radius_km=20,
            max_results=5,
        )

        # Specialist should rank first despite lower rating
        assert ranked[0]["place_id"] == "specialist"

    def test_max_results_limits_output(self):
        """Only max_results candidates should be returned."""
        candidates = [
            _make_candidate(place_id=f"p{i}", rating=4.0 - i * 0.1)
            for i in range(10)
        ]
        ranked = score_and_rank_candidates(
            candidates=candidates,
            goal_outcomes=["general health"],
            main_issue=None,
            diagnoses=[],
            care_style="medical",
            preferences=[],
            avoidances=[],
            visit_mode="either",
            radius_km=20,
            max_results=3,
        )
        assert len(ranked) == 3


class TestFitReasons:
    """Verify fit reasons tie back to user goals and preferences."""

    def test_reasons_reference_goal_outcomes(self):
        """Fit reasons should include the user's stated goals."""
        candidate = _make_candidate(
            category="acupuncture",
            is_physician=False,
            rating=4.5,
            review_count=80,
        )
        sub_scores = {
            "outcome_alignment": 80.0,
            "symptom_alignment": 50.0,
            "care_style_alignment": 100.0,
            "preference_alignment": 75.0,
            "review_quality": 70.0,
            "accessibility": 60.0,
        }
        reasons = generate_fit_reasons(
            candidate=candidate,
            sub_scores=sub_scores,
            goal_outcomes=["reduce chronic pain"],
            preferences=["non-pharmacologic"],
            avoidances=["opioids"],
        )
        # Should contain at least one reason referencing the goal
        goal_reasons = [r for r in reasons if "reduce chronic pain" in r.lower()]
        assert len(goal_reasons) >= 1

    def test_reasons_reference_preference(self):
        """Fit reasons should mention matched preferences."""
        candidate = _make_candidate(category="yoga", is_physician=False)
        sub_scores = {
            "outcome_alignment": 70.0,
            "symptom_alignment": 50.0,
            "care_style_alignment": 100.0,
            "preference_alignment": 75.0,
            "review_quality": 50.0,
            "accessibility": 60.0,
        }
        reasons = generate_fit_reasons(
            candidate=candidate,
            sub_scores=sub_scores,
            goal_outcomes=["reduce stress"],
            preferences=["mind-body"],
            avoidances=[],
        )
        pref_reasons = [r for r in reasons if "mind-body" in r.lower()]
        assert len(pref_reasons) >= 1

    def test_minimum_two_reasons(self):
        """Every provider should have at least 2 fit reasons."""
        candidate = _make_candidate(
            category="other",
            is_physician=False,
            rating=None,
            review_count=None,
        )
        sub_scores = {
            "outcome_alignment": 30.0,
            "symptom_alignment": 30.0,
            "care_style_alignment": 30.0,
            "preference_alignment": 30.0,
            "review_quality": 30.0,
            "accessibility": 30.0,
        }
        reasons = generate_fit_reasons(
            candidate=candidate,
            sub_scores=sub_scores,
            goal_outcomes=["general health"],
            preferences=[],
            avoidances=[],
        )
        assert len(reasons) >= 2

    def test_reasons_capped_at_five(self):
        """No provider should have more than 5 fit reasons."""
        candidate = _make_candidate(
            category="acupuncture",
            is_physician=False,
            npi_verified=True,
            credentials=["LAc"],
            rating=4.8,
            review_count=200,
            distance_km=1.5,
        )
        sub_scores = {
            "outcome_alignment": 95.0,
            "symptom_alignment": 90.0,
            "care_style_alignment": 100.0,
            "preference_alignment": 90.0,
            "review_quality": 90.0,
            "accessibility": 95.0,
        }
        reasons = generate_fit_reasons(
            candidate=candidate,
            sub_scores=sub_scores,
            goal_outcomes=["reduce pain", "improve sleep"],
            preferences=["non-pharmacologic", "holistic"],
            avoidances=["opioids"],
        )
        assert len(reasons) <= 5
