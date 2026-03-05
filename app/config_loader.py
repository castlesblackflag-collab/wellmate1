"""Load and validate YAML configuration files at startup."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

_CONFIG_DIR = Path(__file__).parent / "config"


def _load_yaml(filename: str) -> dict:
    path = _CONFIG_DIR / filename
    with open(path, "r") as f:
        return yaml.safe_load(f)


class Config:
    """Immutable configuration loaded once at import time."""

    def __init__(self) -> None:
        mappings = _load_yaml("mappings.yaml")
        weights_cfg = _load_yaml("weights.yaml")

        # Mappings
        self.outcome_to_modalities: dict = mappings.get("outcome_to_modalities", {})
        self.symptom_to_specialties: dict = mappings.get("symptom_to_specialties", {})
        self.preference_signals: dict = mappings.get("preference_signals", {})
        self.avoidance_signals: dict = mappings.get("avoidance_signals", {})
        self.category_to_places_queries: dict = mappings.get("category_to_places_queries", {})
        self.urgent_symptoms: list[str] = mappings.get("urgent_symptoms", [])

        # Scoring weights (priority: access > accessibility > contact > review > preference > care style > symptom > outcome)
        sw = weights_cfg.get("scoring_weights", {})
        self.w_data_completeness: float = sw.get("data_completeness", 0.20)
        self.w_accessibility: float = sw.get("accessibility", 0.20)
        self.w_contact: float = sw.get("contact_availability", 0.18)
        self.w_review: float = sw.get("review_quality", 0.15)
        self.w_preference: float = sw.get("preference_alignment", 0.10)
        self.w_care_style: float = sw.get("care_style_alignment", 0.07)
        self.w_symptom: float = sw.get("symptom_alignment", 0.05)
        self.w_outcome: float = sw.get("outcome_alignment", 0.05)

        # Operational knobs
        self.npi_match_threshold: float = weights_cfg.get("npi_match_threshold", 0.75)
        self.max_place_detail_calls: int = weights_cfg.get("max_place_detail_calls", 10)
        self.max_search_queries: int = weights_cfg.get("max_search_queries", 4)
        self.geocode_cache_ttl: int = weights_cfg.get("geocode_cache_ttl_seconds", 86400)
        self.places_cache_ttl: int = weights_cfg.get("places_cache_ttl_seconds", 3600)
        self.upstream_timeout: int = weights_cfg.get("upstream_timeout_seconds", 8)

    @property
    def places_api_key(self) -> str:
        key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
        if not key:
            raise RuntimeError("GOOGLE_PLACES_API_KEY environment variable is not set")
        return key


# Singleton instance
cfg = Config()
