"""
Wellmate Practitioner Finder POC - Streamlit Demo App

A local proof-of-concept for finding and ranking practitioners
based on user preferences, symptoms, and accessibility needs.
"""

import logging
import os

import streamlit as st

from practitioner_finder_poc.config.practitioner_types import PRACTITIONER_TYPE_NAMES
from practitioner_finder_poc.mock_data import (
    MOCK_PROVIDERS,
    get_mock_npi_result,
    get_mock_zip_coords,
)
from practitioner_finder_poc.services.google_places import (
    extract_place_info,
    get_place_details,
    search_nearby,
)
from practitioner_finder_poc.services.npi_registry import is_npi_eligible, query_npi
from practitioner_finder_poc.services.review_summary import summarize_reviews
from practitioner_finder_poc.services.scoring import score_practitioner
from practitioner_finder_poc.utils.geography import zip_to_latlng

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- UI Options ---

SYMPTOM_OPTIONS = [
    "pain",
    "addiction",
    "gastrointestinal distress",
    "fatigue",
    "anxiety",
    "inflammation",
]

ACCESSIBILITY_OPTIONS = [
    "telemedicine preferred",
    "phone number listed",
    "website listed",
    "hours of operation listed",
]

PREFERENCE_OPTIONS = [
    "whole health",
    "naturopathic",
    "non-pharmacologic",
    "integrative",
    "conventional medical",
]

OUTCOME_OPTIONS = [
    "walking without pain",
    "avoiding long-term opioids",
    "improving digestion",
    "reducing stress",
]


def main():
    st.set_page_config(page_title="Wellmate Practitioner Finder", layout="wide")

    st.title("Wellmate Practitioner Finder POC")
    st.markdown(
        "Find up to 5 practitioners in your area, ranked by relevance to your needs. "
        "This is a local proof-of-concept demo."
    )

    # Check API availability
    has_api_key = bool(os.environ.get("PLACES_API_KEY"))
    use_mock = st.sidebar.checkbox(
        "Use mock data (demo mode)",
        value=not has_api_key,
        help="Use sample data instead of live API calls. Enabled by default when PLACES_API_KEY is not set.",
    )

    if not has_api_key and not use_mock:
        st.sidebar.warning("PLACES_API_KEY not set. Enable mock data or set the environment variable.")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**About this POC**")
    st.sidebar.markdown(
        "Symptom and outcome matching are soft ranking signals only, "
        "not medical triage or exclusion logic. "
        "NPI cross-referencing is only attempted for likely medical providers."
    )

    # --- Input Form ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Location & Search")
        zip_code = st.text_input("ZIP Code", value="78701", max_chars=5)
        radius_miles = st.slider("Search Radius (miles)", min_value=1, max_value=50, value=10)

        st.subheader("Practitioner Types")
        practitioner_types = st.multiselect(
            "Select practitioner type(s)",
            options=PRACTITIONER_TYPE_NAMES,
            default=["physical therapist"],
        )

        st.subheader("Symptom Keywords")
        symptoms = st.multiselect(
            "Select symptom(s) (optional - soft ranking signal)",
            options=SYMPTOM_OPTIONS,
        )

    with col2:
        st.subheader("Accessibility Preferences")
        accessibility_prefs = st.multiselect(
            "Select accessibility/convenience preferences",
            options=ACCESSIBILITY_OPTIONS,
        )

        st.subheader("Care Preference Weighting")
        preference_weights = st.multiselect(
            "Select care approach preference(s)",
            options=PREFERENCE_OPTIONS,
        )

        st.subheader("Preferred Outcomes")
        preferred_outcomes = st.multiselect(
            "Select preferred outcome(s) (optional - very soft modifier)",
            options=OUTCOME_OPTIONS,
        )

    st.markdown("---")

    # --- Search Button ---
    if st.button("Search Practitioners", type="primary"):
        if not zip_code or len(zip_code) != 5 or not zip_code.isdigit():
            st.error("Please enter a valid 5-digit US ZIP code.")
            return

        if not practitioner_types:
            st.error("Please select at least one practitioner type.")
            return

        with st.spinner("Searching for practitioners..."):
            results = _run_search(
                zip_code=zip_code,
                radius_miles=radius_miles,
                practitioner_types=practitioner_types,
                symptoms=symptoms,
                accessibility_prefs=accessibility_prefs,
                preference_weights=preference_weights,
                preferred_outcomes=preferred_outcomes,
                use_mock=use_mock,
            )

        if not results:
            st.warning("No practitioners found. Try widening your search radius or changing practitioner types.")
            return

        st.success(f"Found {len(results)} practitioner(s), ranked by relevance:")
        st.markdown("---")

        for i, result in enumerate(results, 1):
            _render_result(i, result)


def _run_search(
    zip_code: str,
    radius_miles: float,
    practitioner_types: list[str],
    symptoms: list[str],
    accessibility_prefs: list[str],
    preference_weights: list[str],
    preferred_outcomes: list[str],
    use_mock: bool,
) -> list[dict]:
    """Execute the full search, scoring, and ranking pipeline."""

    # Step 1: Geocode ZIP
    if use_mock:
        coords = get_mock_zip_coords(zip_code)
    else:
        coords = zip_to_latlng(zip_code)

    if not coords:
        st.error(f"Could not geocode ZIP code {zip_code}.")
        return []

    center_lat, center_lng = coords

    # Step 2: Get providers
    if use_mock:
        providers = MOCK_PROVIDERS
    else:
        # Build search terms from selected practitioner types
        from practitioner_finder_poc.config.practitioner_types import PRACTITIONER_TYPES
        all_terms = []
        for pt in practitioner_types:
            info = PRACTITIONER_TYPES.get(pt, {})
            all_terms.extend(info.get("search_terms", [pt]))

        raw_places = search_nearby(center_lat, center_lng, radius_miles, all_terms)

        if not raw_places:
            st.warning("No results from Places API. Falling back to mock data for demo.")
            providers = MOCK_PROVIDERS
            use_mock = True
        else:
            # Fetch details for top candidates (limit API calls)
            providers = []
            for place in raw_places[:15]:
                pid = place.get("id")
                details = get_place_details(pid) if pid else None
                if details:
                    providers.append(extract_place_info(details))
                else:
                    providers.append(extract_place_info(place))

    # Step 3: NPI cross-referencing
    npi_eligible = is_npi_eligible(practitioner_types)
    npi_results = {}

    for provider in providers:
        pid = provider.get("place_id", "")
        if use_mock:
            npi_results[pid] = get_mock_npi_result(pid)
        elif npi_eligible:
            npi_results[pid] = query_npi(
                provider.get("name", ""),
                provider.get("address"),
                practitioner_types,
            )
        else:
            npi_results[pid] = {
                "status": "no API match available",
                "npi_number": None,
                "npi_name": None,
                "taxonomy": None,
                "confidence": 0.0,
            }

    # Step 4: Score and rank
    scored = []
    for provider in providers:
        pid = provider.get("place_id", "")
        npi_result = npi_results.get(pid, {"confidence": 0.0})

        score_result = score_practitioner(
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

        # Review summary
        review_summary = summarize_reviews(provider.get("review_texts", []))

        scored.append({
            "provider": provider,
            "score": score_result,
            "npi": npi_result,
            "review_summary": review_summary,
        })

    # Sort by total score descending, return top 5
    scored.sort(key=lambda x: x["score"]["total_score"], reverse=True)
    return scored[:5]


def _render_result(rank: int, result: dict):
    """Render a single practitioner result card."""
    provider = result["provider"]
    score = result["score"]
    npi = result["npi"]
    review_summary = result["review_summary"]

    # Score label
    total = score["total_score"]
    if total >= 70:
        score_label = "Strong Match"
    elif total >= 50:
        score_label = "Good Match"
    elif total >= 30:
        score_label = "Moderate Match"
    else:
        score_label = "Weak Match"

    with st.container():
        st.markdown(f"### {rank}. {provider.get('name', 'Unknown Provider')}")

        col_a, col_b = st.columns([2, 1])

        with col_a:
            if provider.get("address"):
                st.markdown(f"**Address:** {provider['address']}")
            if provider.get("phone"):
                st.markdown(f"**Phone:** {provider['phone']}")
            if provider.get("website"):
                st.markdown(f"**Website:** {provider['website']}")
            if provider.get("hours"):
                st.markdown(f"**Hours:** {provider['hours']}")
            if provider.get("rating") is not None:
                stars = provider["rating"]
                count = provider.get("review_count", 0)
                st.markdown(f"**Rating:** {stars}/5 ({count} reviews)")

        with col_b:
            st.metric("Relevance Score", f"{total:.1f}/100")
            st.caption(score_label)

        # Match blurb
        st.markdown(f"**Why this ranked:** {score['blurb']}")

        # NPI status
        npi_status = npi.get("status", "no API match available")
        if npi_status == "NPI matched":
            npi_detail = f"NPI #{npi.get('npi_number', 'N/A')}"
            if npi.get("taxonomy"):
                npi_detail += f" ({npi['taxonomy']})"
            st.markdown(f"**NPI Status:** {npi_status} - {npi_detail}")
        elif npi_status == "possible NPI match":
            st.markdown(f"**NPI Status:** {npi_status}")
        else:
            st.markdown(f"**NPI Status:** {npi_status}")

        # Review summary
        if review_summary:
            st.markdown(f"**Review highlights:** {review_summary}")
        else:
            st.markdown("**Review highlights:** No review text available")

        st.markdown("---")


if __name__ == "__main__":
    main()
