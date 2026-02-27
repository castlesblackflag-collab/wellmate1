# Wellmate Practitioner Finder

## Project Overview
Cloud Run backend service that powers the Wellmate Practitioner Finder Playbook.
Exposes a single `POST /search_practitioners` endpoint designed for Google
Conversational Agent / Playbooks via OpenAPI Tool registration.

## Architecture
- **Framework**: FastAPI + Pydantic (strict schema enforcement, auto OpenAPI)
- **Runtime**: Python 3.12 on Cloud Run
- **External APIs**: Google Places (candidate retrieval), NPPES NPI Registry (physician verification)
- **Config**: YAML mapping files in `app/config/` (versioned in repo)

## Commands
- Run server: `uvicorn app.main:app --reload`
- Run tests: `pytest tests/ -v`
- Build container: `docker build -t wellmate-finder .`

## Code Layout
```
app/
  main.py              # FastAPI app, route handler, error middleware
  schema.py            # Pydantic request/response models (tool contract)
  geocode.py           # location_text -> lat/lng with caching
  places_client.py     # Google Places search + details
  npi_client.py        # NPPES NPI Registry queries
  matcher.py           # Place-to-NPI fuzzy matching
  scoring.py           # Deterministic scoring + fit reason generation
  config_loader.py     # YAML config loading and validation
  config/
    mappings.yaml      # symptoms/outcomes -> specialties/modalities
    weights.yaml       # scoring weight configuration
tests/
  test_scoring.py      # Scoring unit tests
  test_schema.py       # Schema validation tests
search_practitioners.yaml  # OpenAPI spec for Agent Builder
```

## Key Design Rules
- Backend returns facts and structured reasons only; never prose paragraphs
- Response shape is always identical (results/meta/warnings/error)
- No fabrication: if data is missing, use null, never invent
- Scoring is deterministic and config-driven, not LLM-based
- No emoji in code or outputs
