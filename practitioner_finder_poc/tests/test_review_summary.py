"""Tests for review summary behavior."""

from practitioner_finder_poc.services.review_summary import summarize_reviews, _extract_snippet


class TestSummarizeReviews:
    def test_with_reviews(self):
        reviews = [
            "Great doctor who listens to patients. Very thorough examination.",
            "Helped me with chronic pain management. Highly recommend.",
        ]
        summary = summarize_reviews(reviews)
        assert summary is not None
        assert len(summary) > 0
        assert len(summary) <= 200

    def test_no_reviews_returns_none(self):
        assert summarize_reviews([]) is None

    def test_empty_strings_returns_none(self):
        assert summarize_reviews(["", "", ""]) is None

    def test_single_short_review(self):
        summary = summarize_reviews(["Good doctor."])
        assert summary is not None
        assert "Good doctor" in summary

    def test_long_reviews_truncated(self):
        long_review = "This is a very " + "long " * 100 + "review."
        summary = summarize_reviews([long_review], max_length=100)
        assert summary is not None
        assert len(summary) <= 100

    def test_multiple_reviews_combined(self):
        reviews = [
            "First review about pain management.",
            "Second review about friendly staff.",
            "Third review about clean facility.",
        ]
        summary = summarize_reviews(reviews)
        assert summary is not None
        assert "|" in summary  # Reviews joined with |


class TestExtractSnippet:
    def test_short_text(self):
        snippet = _extract_snippet("Short review.")
        assert snippet == "Short review."

    def test_long_text_truncated(self):
        text = "A" * 200
        snippet = _extract_snippet(text, max_snippet=80)
        assert len(snippet) <= 83  # 80 + "..."

    def test_empty_text(self):
        assert _extract_snippet("") == ""

    def test_sentence_boundary(self):
        text = "First sentence is good. Second sentence is also fine but longer and we probably want the first one."
        snippet = _extract_snippet(text, max_snippet=50)
        assert "First sentence is good" in snippet
