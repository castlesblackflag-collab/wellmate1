"""Tests for preferred outcome soft modifier logic."""

from practitioner_finder_poc.services.scoring import _score_outcome_alignment


class TestOutcomeModifier:
    def test_walking_without_pain_boosts_pt(self):
        score = _score_outcome_alignment(
            ["physical therapist"], ["walking without pain"]
        )
        assert score > 0.5

    def test_avoiding_opioids_boosts_integrative(self):
        score = _score_outcome_alignment(
            ["integrative medicine"], ["avoiding long-term opioids"]
        )
        assert score > 0.5

    def test_improving_digestion_boosts_gi(self):
        score = _score_outcome_alignment(
            ["gastroenterologist"], ["improving digestion"]
        )
        assert score > 0.5

    def test_reducing_stress_boosts_massage(self):
        score = _score_outcome_alignment(
            ["massage therapist"], ["reducing stress"]
        )
        assert score > 0.5

    def test_unrelated_types_score_low(self):
        score = _score_outcome_alignment(
            ["anesthesiologist"], ["improving digestion"]
        )
        assert score < 0.5

    def test_empty_outcomes_returns_neutral(self):
        score = _score_outcome_alignment(["physical therapist"], [])
        assert score == 0.5

    def test_empty_types_returns_neutral(self):
        score = _score_outcome_alignment([], ["walking without pain"])
        assert score == 0.5

    def test_multiple_outcomes(self):
        score = _score_outcome_alignment(
            ["physical therapist", "integrative medicine"],
            ["walking without pain", "avoiding long-term opioids"],
        )
        assert score > 0.5

    def test_never_exceeds_one(self):
        score = _score_outcome_alignment(
            ["physical therapist", "chiropractor", "acupuncturist", "integrative medicine"],
            ["walking without pain"],
        )
        assert score <= 1.0
