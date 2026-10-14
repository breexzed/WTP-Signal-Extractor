from __future__ import annotations

from copy import deepcopy
from typing import Any

REGISTER_NAMES = [
    "operator_vernacular",
    "industry_professional",
    "complaint_register",
    "consequence_register",
    "intermediary_register",
    "trade_publication",
    "job_listing_register",
    "year_specific",
    "gatekeeper_self_description",
]

PHASE_VALUES = {"0", "1", "2", "3", "3.5", "mixed", "unknown"}
SIGNAL_DENSITY_VALUES = {"low", "medium", "high"}
SOURCE_TYPE_VALUES = {
    "operator_interview",
    "panel",
    "vendor_demo",
    "trade_discussion",
    "unknown",
}
SPEAKER_TYPE_VALUES = {"operator", "intermediary", "mixed", "unknown"}
TRANSCRIPT_STATUS_VALUES = {"fetched", "pasted", "failed"}
INPUT_TYPE_VALUES = {"youtube_url", "pasted_transcript"}
ENTITY_KIND_VALUES = {
    "platform",
    "software",
    "institution",
    "distributor",
    "person",
    "certification_body",
    "other",
}
ENTITY_RELATIONSHIP_VALUES = {"dependent", "frustrated", "switching", "praise", "unknown"}
GATEKEEPER_RELATIONSHIP_VALUES = {
    "dependent",
    "frustrated",
    "loyal",
    "switching_away",
    "unknown",
}
DEPENDENCY_TYPE_VALUES = {
    "structural_friction",
    "social_authority",
    "information_asymmetry",
    "platform",
    "unknown",
}
GATEKEEPER_TYPE_VALUES = {"Type1", "Type2", "Type3", "Type4", "unknown"}
CONFIDENCE_VALUES = {"low", "medium", "high"}
REGISTER_STRENGTH_VALUES = {"low", "medium", "high"}


def canonical_phase(value: str | None) -> str:
    if value is None:
        return "unknown"
    stripped = str(value).strip()
    if stripped in PHASE_VALUES:
        return stripped
    return "unknown"


def empty_search_language_feedback() -> dict[str, Any]:
    return {
        "likely_too_generic": False,
        "too_vendor_heavy": False,
        "off_phase": False,
        "likely_operator_facing": False,
        "likely_gatekeeper_facing": False,
        "reason": "Not provided.",
    }


def empty_result() -> dict[str, Any]:
    return {
        "schema_version": "2",
        "source": {
            "source_id": "",
            "url": None,
            "video_id": None,
            "input_type": "pasted_transcript",
            "transcript_status": "pasted",
            "source_type": "unknown",
            "speaker_type": "unknown",
            "transcript_chars": 0,
            "transcript_path": None,
        },
        "provenance": {
            "origin_cluster_id": None,
            "origin_register": None,
            "query_used": None,
        },
        "pass1": {
            "behavior_signals": [],
            "opinion_signals": [],
            "summary": {
                "total_high_signal_moments": 0,
                "dominant_pain_category": "None found.",
                "confidence_level": "Not provided.",
            },
        },
        "pass2": {
            "cascade_indicators": [],
            "gatekeeper_mentions": [],
            "position_intelligence": [],
            "subniche_culture_signals": [],
            "summary": {
                "strongest_cascade_found": "None found.",
                "highest_signal_gatekeeper_mention": "None found.",
                "position_intelligence_confidence": "low",
                "recommended_next_action": "Not provided.",
            },
        },
        "diagnostics": {
            "phase_fit": "unknown",
            "signal_density": "low",
            "register_alignment": [],
            "named_entities": [],
            "gatekeepers": [],
            "search_language_feedback": empty_search_language_feedback(),
            "recommended_next_phase": "unknown",
            "diagnostic_notes": [],
            "field_sources": {},
        },
        "combined_summary": {
            "top_3_actionable_signals": [],
            "hypothesis_worth_testing": "None found.",
        },
        "parse_warnings": [],
        "raw_output": None,
        "status": "ok",
        "evidence": {"checked": False, "total": 0, "verified": 0, "approximate": 0,
                     "stitched": 0, "not_found": 0, "items": []},
        "run": {},
        "artifacts": {},
    }


def merge_result(
    source: dict[str, Any],
    provenance: dict[str, Any],
    pass1: dict[str, Any],
    pass2: dict[str, Any],
    diagnostics: dict[str, Any],
    combined_summary: dict[str, Any],
    parse_warnings: list[str],
    raw_output: str | None,
) -> dict[str, Any]:
    result = empty_result()
    result["source"].update(source)
    result["provenance"].update(provenance)
    result["pass1"].update(pass1)
    result["pass2"].update(pass2)
    result["diagnostics"].update(diagnostics)
    result["combined_summary"].update(combined_summary)
    result["parse_warnings"] = list(parse_warnings)
    result["raw_output"] = raw_output
    return result


def deep_copy_result(result: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(result)
