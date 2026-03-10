"""Mock integration test using sample provider records."""

from practitioner_finder_poc.mock_data import MOCK_PROVIDERS, get_mock_npi_result
from practitioner_finder_poc.services.review_summary import summarize_reviews
from practitioner_finder_poc.services.scoring import score_practitioner


class TestIntegration:
    """Integration test: score and rank mock providers end-to-end."""

    def test_full_pipeline_returns_ranked_results(self):
        center_lat, center_lng = 30.2672, -97.7431
        radius_miles = 10
        practitioner_types = ["physical therapist", "integrative medicine"]
        symptoms = ["pain"]
        accessibility_prefs = ["phone number listed", "website listed"]
        preference_weights = ["non-pharmacologic"]
        preferred_outcomes = ["walking without pain"]

        scored = []
        for provider in MOCK_PROVIDERS:
            pid = provider["place_id"]
            npi_result = get_mock_npi_result(pid)

            result = score_practitioner(
                provider=provider,
                center_lat=center_lat,
                center_lng=center_lng,
                radius_miles=radius_miles,
                practitioner_types=practitioner_types,
                symptoms=symptoms,
                accessibility_prefs=accessibility_prefs,
                preference_weights=preference_weights,
                preferred_outcomes=preferred_outcomes,
                npi_result=npi_result,
            )

            review_summary = summarize_reviews(provider.get("review_texts", []))

            scored.append({
                "name": provider["name"],
                "score": result["total_score"],
                "blurb": result["blurb"],
                "npi_status": npi_result["status"],
                "review_summary": review_summary,
            })

        # Sort by score descending
        scored.sort(key=lambda x: x["score"], reverse=True)
        top5 = scored[:5]

        # Basic assertions
        assert len(top5) == 5
        assert all(r["score"] >= 0 for r in top5)
        assert all(r["score"] <= 100 for r in top5)
        assert all(r["blurb"] for r in top5)

        # Scores should be in descending order
        scores = [r["score"] for r in top5]
        assert scores == sorted(scores, reverse=True)

        # NPI statuses should be valid
        valid_statuses = {"NPI matched", "possible NPI match", "no API match available"}
        for r in top5:
            assert r["npi_status"] in valid_statuses

    def test_different_preferences_change_ranking(self):
        """Verify that changing preferences actually changes the ranking order."""
        center_lat, center_lng = 30.2672, -97.7431

        def rank_with_types(types, prefs):
            scored = []
            for provider in MOCK_PROVIDERS:
                result = score_practitioner(
                    provider=provider,
                    center_lat=center_lat,
                    center_lng=center_lng,
                    radius_miles=10,
                    practitioner_types=types,
                    symptoms=[],
                    accessibility_prefs=[],
                    preference_weights=prefs,
                    preferred_outcomes=[],
                    npi_result={"confidence": 0.0},
                )
                scored.append((provider["name"], result["total_score"]))
            scored.sort(key=lambda x: x[1], reverse=True)
            return [name for name, _ in scored[:5]]

        # Physical therapist search
        pt_ranking = rank_with_types(["physical therapist"], ["non-pharmacologic"])

        # Gastroenterologist search
        gi_ranking = rank_with_types(["gastroenterologist"], ["conventional medical"])

        # Rankings should differ
        assert pt_ranking != gi_ranking

    def test_all_mock_providers_score_without_error(self):
        """Every mock provider should score without raising exceptions."""
        for provider in MOCK_PROVIDERS:
            result = score_practitioner(
                provider=provider,
                center_lat=30.27,
                center_lng=-97.74,
                radius_miles=10,
                practitioner_types=["general practitioner"],
                symptoms=["fatigue"],
                accessibility_prefs=["phone number listed"],
                preference_weights=["integrative"],
                preferred_outcomes=["reducing stress"],
                npi_result=get_mock_npi_result(provider["place_id"]),
            )
            assert isinstance(result["total_score"], float)
            assert isinstance(result["blurb"], str)
