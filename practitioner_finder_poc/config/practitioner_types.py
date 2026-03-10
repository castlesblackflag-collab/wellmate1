"""
Practitioner type definitions, Google Places search terms,
and NPI eligibility flags.
"""

PRACTITIONER_TYPES = {
    "general practitioner": {
        "search_terms": ["general practitioner", "family doctor", "family medicine"],
        "npi_eligible": True,
        "npi_taxonomy_hint": "family",
    },
    "dietitian": {
        "search_terms": ["dietitian", "registered dietitian", "nutritionist"],
        "npi_eligible": True,
        "npi_taxonomy_hint": "dietitian",
    },
    "acupuncturist": {
        "search_terms": ["acupuncturist", "acupuncture"],
        "npi_eligible": False,
        "npi_taxonomy_hint": None,
    },
    "physical therapist": {
        "search_terms": ["physical therapist", "physical therapy", "physiotherapy"],
        "npi_eligible": True,
        "npi_taxonomy_hint": "physical therap",
    },
    "anesthesiologist": {
        "search_terms": ["anesthesiologist", "anesthesiology", "pain management doctor"],
        "npi_eligible": True,
        "npi_taxonomy_hint": "anesthesiology",
    },
    "chiropractor": {
        "search_terms": ["chiropractor", "chiropractic"],
        "npi_eligible": True,
        "npi_taxonomy_hint": "chiropractic",
    },
    "massage therapist": {
        "search_terms": ["massage therapist", "massage therapy"],
        "npi_eligible": False,
        "npi_taxonomy_hint": None,
    },
    "naturopath": {
        "search_terms": ["naturopath", "naturopathic doctor", "naturopathic medicine"],
        "npi_eligible": False,
        "npi_taxonomy_hint": None,
    },
    "pain clinic": {
        "search_terms": ["pain clinic", "pain management clinic", "pain center"],
        "npi_eligible": True,
        "npi_taxonomy_hint": "pain",
    },
    "gastroenterologist": {
        "search_terms": ["gastroenterologist", "gastroenterology", "GI doctor"],
        "npi_eligible": True,
        "npi_taxonomy_hint": "gastroenterology",
    },
    "integrative medicine": {
        "search_terms": ["integrative medicine", "integrative health", "holistic medicine"],
        "npi_eligible": True,
        "npi_taxonomy_hint": "integrative",
    },
    "primary care": {
        "search_terms": ["primary care physician", "primary care doctor", "internal medicine"],
        "npi_eligible": True,
        "npi_taxonomy_hint": "internal medicine",
    },
}

# All available practitioner type names
PRACTITIONER_TYPE_NAMES = list(PRACTITIONER_TYPES.keys())
