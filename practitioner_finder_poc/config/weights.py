"""
Editable scoring weights for practitioner ranking.

Adjust these values to change how different factors influence final scores.
All weights should be positive floats. They are normalized during scoring.
"""

SCORING_WEIGHTS = {
    # Core matching
    "practitioner_type_match": 0.30,
    "geographic_proximity": 0.20,
    "rating_and_reviews": 0.15,

    # Accessibility / convenience
    "accessibility_preferences": 0.10,

    # Soft signals
    "symptom_alignment": 0.10,
    "preference_weighting": 0.10,
    "preferred_outcome": 0.03,

    # NPI confidence (medical providers only)
    "npi_confidence": 0.02,
}

# Maximum radius in miles for geographic scoring
MAX_RADIUS_MILES = 50

# Rating scale (Google uses 1-5)
MAX_RATING = 5.0

# Minimum review count to get full review-count credit
REVIEW_COUNT_SATURATION = 50
