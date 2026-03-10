"""Tests for symptom alignment logic."""

from practitioner_finder_poc.services.symptom_mapping import compute_symptom_score


class TestSymptomScore:
    def test_pain_with_relevant_type(self):
        score, reasons = compute_symptom_score(
            symptoms=["pain"],
            practitioner_types_selected=["physical therapist"],
            provider_types=["physiotherapist"],
            review_texts=["Great for chronic pain relief"],
        )
        assert score > 0.0
        assert len(reasons) > 0

    def test_pain_with_irrelevant_type(self):
        score, reasons = compute_symptom_score(
            symptoms=["pain"],
            practitioner_types_selected=["dietitian"],
            provider_types=["health"],
            review_texts=["Great nutritional advice"],
        )
        # Should still return a score (possibly from review keywords) but lower
        assert score < 0.5

    def test_no_symptoms_returns_zero(self):
        score, reasons = compute_symptom_score(
            symptoms=[],
            practitioner_types_selected=["physical therapist"],
            provider_types=["physiotherapist"],
            review_texts=["Great clinic"],
        )
        assert score == 0.0
        assert reasons == []

    def test_multiple_symptoms(self):
        score, reasons = compute_symptom_score(
            symptoms=["pain", "anxiety"],
            practitioner_types_selected=["integrative medicine"],
            provider_types=["health"],
            review_texts=["Helps with chronic pain and anxiety management"],
        )
        assert score > 0.0
        assert len(reasons) >= 1

    def test_review_keyword_matching(self):
        score, reasons = compute_symptom_score(
            symptoms=["gastrointestinal distress"],
            practitioner_types_selected=["gastroenterologist"],
            provider_types=["doctor"],
            review_texts=["Excellent for stomach and digestive problems, IBS treatment"],
        )
        assert score > 0.3
        assert any("reviews mention" in r for r in reasons)

    def test_unknown_symptom_ignored(self):
        score, reasons = compute_symptom_score(
            symptoms=["unknown_rare_condition"],
            practitioner_types_selected=["general practitioner"],
            provider_types=["doctor"],
            review_texts=["Good doctor"],
        )
        assert score == 0.0

    def test_score_capped_at_one(self):
        score, _ = compute_symptom_score(
            symptoms=["pain"],
            practitioner_types_selected=["physical therapist", "chiropractor", "pain clinic"],
            provider_types=["physiotherapist"],
            review_texts=["chronic pain relief back pain joint pain mobility injury treatment"] * 5,
        )
        assert score <= 1.0
