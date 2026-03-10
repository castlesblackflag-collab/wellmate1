"""Tests for NPI match labeling logic."""

from practitioner_finder_poc.services.npi_registry import (
    is_npi_eligible,
    get_taxonomy_hints,
    _name_similarity,
    _extract_name_parts,
    _extract_state_from_address,
)


class TestNPIEligibility:
    def test_medical_types_are_eligible(self):
        assert is_npi_eligible(["general practitioner"]) is True
        assert is_npi_eligible(["physical therapist"]) is True
        assert is_npi_eligible(["gastroenterologist"]) is True
        assert is_npi_eligible(["chiropractor"]) is True

    def test_non_medical_types_not_eligible(self):
        assert is_npi_eligible(["massage therapist"]) is False
        assert is_npi_eligible(["acupuncturist"]) is False
        assert is_npi_eligible(["naturopath"]) is False

    def test_mixed_types_eligible_if_any_medical(self):
        assert is_npi_eligible(["massage therapist", "general practitioner"]) is True

    def test_empty_list(self):
        assert is_npi_eligible([]) is False


class TestTaxonomyHints:
    def test_returns_hints(self):
        hints = get_taxonomy_hints(["general practitioner"])
        assert "family" in hints

    def test_no_hints_for_non_eligible(self):
        hints = get_taxonomy_hints(["massage therapist"])
        assert hints == []


class TestNameSimilarity:
    def test_identical(self):
        assert _name_similarity("john smith", "john smith") == 1.0

    def test_partial_overlap(self):
        score = _name_similarity("john smith md", "john smith")
        assert 0.5 < score < 1.0

    def test_no_overlap(self):
        assert _name_similarity("alice jones", "bob smith") == 0.0

    def test_empty(self):
        assert _name_similarity("", "") == 0.0


class TestNameExtraction:
    def test_simple_name(self):
        first, last = _extract_name_parts("John Smith")
        assert first == "John"
        assert last == "Smith"

    def test_with_title(self):
        first, last = _extract_name_parts("Dr. Sarah Mitchell")
        assert first == "Sarah"
        assert last == "Mitchell"

    def test_organization_name(self):
        first, last = _extract_name_parts("Austin Physical Therapy & Rehabilitation Center")
        assert first == "" and last == ""


class TestStateExtraction:
    def test_standard_address(self):
        state = _extract_state_from_address("123 Main St, Austin, TX 78701")
        assert state == "TX"

    def test_no_state(self):
        state = _extract_state_from_address("123 Main St, Austin")
        assert state == ""

    def test_none_address(self):
        state = _extract_state_from_address(None)
        assert state == ""
