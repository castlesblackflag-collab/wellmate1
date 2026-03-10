# Wellmate Practitioner Finder POC

A local proof-of-concept application that helps users find up to 5 practitioners
in their region using Google Places API (New), with optional NPI Registry
cross-referencing for likely medical providers.

## What It Does

- Accepts user inputs: ZIP code, search radius, practitioner types, symptoms,
  accessibility preferences, care approach preferences, and preferred outcomes
- Searches for practitioners via Google Places API (New) or uses built-in mock data
- Scores and ranks results using deterministic, configurable weighted logic
- Cross-references likely medical providers against the NPPES NPI Registry
- Displays up to 5 ranked results with relevance scores, match explanations,
  review summaries, and NPI status

## Setup

### Requirements

- Python 3.10+
- pip

### Install Dependencies

```bash
cd practitioner_finder_poc
pip install -r requirements.txt
```

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `PLACES_API_KEY` | Optional | Google Places API (New) key. If not set, use mock data mode. |

Set it before running:

```bash
export PLACES_API_KEY=your_key_here
```

## How to Run Locally

From the repository root:

```bash
streamlit run practitioner_finder_poc/app.py
```

The app opens in your browser. If `PLACES_API_KEY` is not set, the "Use mock
data" checkbox is enabled by default so you can demo the full scoring and
ranking pipeline with sample data.

## How to Run Tests

```bash
python -m pytest practitioner_finder_poc/tests/ -v
```

## Project Structure

```
practitioner_finder_poc/
  app.py                        # Streamlit UI
  mock_data.py                  # Mock provider data for demo mode
  services/
    google_places.py            # Google Places API (New) client
    npi_registry.py             # NPPES NPI Registry cross-referencing
    scoring.py                  # Deterministic weighted scoring
    symptom_mapping.py          # Symptom-to-practitioner soft signals
    review_summary.py           # Conservative review summarization
  utils/
    geography.py                # ZIP-to-lat/lng, haversine distance
  config/
    weights.py                  # Editable scoring weights
    practitioner_types.py       # Type definitions & NPI eligibility
  tests/
    test_scoring.py             # Scoring logic tests
    test_symptom_mapping.py     # Symptom alignment tests
    test_outcome_modifier.py    # Outcome soft modifier tests
    test_npi_labeling.py        # NPI match label tests
    test_review_summary.py      # Review summary tests
    test_integration.py         # Mock integration test
```

## Important Notes

### NPI Cross-Referencing

NPI cross-referencing is only attempted for likely medical providers (e.g.,
physicians, physical therapists, chiropractors, gastroenterologists). It is
**not** attempted for massage therapists, acupuncturists, or naturopaths, as
these provider types are often not reliably represented in the NPI registry.

NPI match status is reported as one of:
- **NPI matched** - high-confidence name and taxonomy match found
- **possible NPI match** - partial match found
- **no API match available** - no match attempted or no match found

Providers are not penalized for lacking an NPI match.

### Symptom and Outcome Matching

Symptom alignment and preferred outcome matching are **soft ranking signals
only**. They contribute small boosts to relevance scores where plausible
alignment exists. They are **never** used as exclusion filters or medical
triage logic. No claims of medical suitability are made.

### Scoring Weights

All scoring weights are defined in `config/weights.py` and can be adjusted.
The scoring is fully deterministic and config-driven.

## Limitations

- This is a local POC only; not integrated with any cloud services or deployment targets
- No appointment booking, insurance checking, or outcome guarantees
- Telemedicine availability is inferred from clues only, not verified
- Review summaries are brief excerpts, not AI-generated analysis
- NPI matching uses conservative heuristics and may miss valid matches
- Symptom and outcome matching use keyword-based heuristics, not clinical logic
- ZIP code geocoding uses a free API (zippopotam.us) with limited precision
- Google Places API quotas and rate limits may affect live searches
