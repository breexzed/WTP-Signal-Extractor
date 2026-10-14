from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from schemas import (
    CONFIDENCE_VALUES,
    DEPENDENCY_TYPE_VALUES,
    ENTITY_KIND_VALUES,
    ENTITY_RELATIONSHIP_VALUES,
    GATEKEEPER_RELATIONSHIP_VALUES,
    GATEKEEPER_TYPE_VALUES,
    PHASE_VALUES,
    REGISTER_NAMES,
    SIGNAL_DENSITY_VALUES,
    SOURCE_TYPE_VALUES,
    SPEAKER_TYPE_VALUES,
)


GENERIC_QUERY_TERMS = {
    "interview",
    "podcast",
    "youtube",
    "industry",
    "business",
    "operator",
    "pain points",
}


def normalize_confidence(value: str | None, fallback: str = "low") -> str:
    normalized = (value or fallback).strip().lower()
    if normalized in CONFIDENCE_VALUES:
        return normalized
    return fallback


def normalize_dependency_type(value: str | None) -> str:
    normalized = (value or "unknown").strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in DEPENDENCY_TYPE_VALUES:
        return normalized
    if "platform" in normalized:
        return "platform"
    if "authority" in normalized:
        return "social_authority"
    if "information" in normalized:
        return "information_asymmetry"
    if "structural" in normalized:
        return "structural_friction"
    return "unknown"


def normalize_gatekeeper_relationship(value: str | None) -> str:
    normalized = (value or "unknown").strip().lower().replace(" ", "_")
    if normalized in GATEKEEPER_RELATIONSHIP_VALUES:
        return normalized
    if normalized == "switching":
        return "switching_away"
    return "unknown"


def normalize_entity_relationship(value: str | None) -> str:
    normalized = (value or "unknown").strip().lower().replace(" ", "_")
    if normalized == "switching_away":
        return "switching"
    if normalized in ENTITY_RELATIONSHIP_VALUES:
        return normalized
    return "unknown"


def normalize_entity_kind(value: str | None, entity_name: str = "") -> str:
    normalized = (value or "").strip().lower().replace(" ", "_")
    if normalized in ENTITY_KIND_VALUES:
        return normalized

    lowered = entity_name.lower()
    if any(token in lowered for token in ("platform", "marketplace")):
        return "platform"
    if any(token in lowered for token in ("software", "app", "crm", "tool")):
        return "software"
    if any(token in lowered for token in ("board", "association", "council", "agency")):
        return "institution"
    if any(token in lowered for token in ("distributor", "wholesaler", "supplier")):
        return "distributor"
    if any(token in lowered for token in ("certification", "licensed", "accreditation")):
        return "certification_body"
    if len(entity_name.split()) >= 2 and entity_name.istitle():
        return "person"
    return "other"


def model_hint(hints: dict[str, Any], key: str, allowed: set[str]) -> str | None:
    """The model's value for key if it is in the allowed vocabulary, else None.
    A missing or invalid answer must not pass for a real one."""
    value = hints.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    if key != "phase_fit":
        normalized = normalized.lower()
    return normalized if normalized in allowed else None


def infer_gatekeeper_type(dependency_type: str, entity_kind: str) -> str:
    if dependency_type == "platform" or entity_kind == "platform":
        return "Type4"
    if dependency_type == "social_authority":
        return "Type2"
    if dependency_type == "information_asymmetry":
        return "Type3"
    if dependency_type == "structural_friction":
        return "Type1"
    return "unknown"


def infer_source_type(transcript_text: str, diagnostic_hints: dict[str, Any]) -> str:
    hinted = model_hint(diagnostic_hints, "source_type", SOURCE_TYPE_VALUES)
    if hinted:
        return hinted

    lowered = transcript_text.lower()
    if any(token in lowered for token in ("demo", "walkthrough", "feature", "pricing page")):
        return "vendor_demo"
    if "moderator" in lowered or lowered.count("speaker") > 2:
        return "panel"
    if any(token in lowered for token in ("conference", "industry report", "trade show", "panel")):
        return "trade_discussion"
    if any(token in lowered for token in ("we paid", "our clients", "our workflow", "we still depend")):
        return "operator_interview"
    return "unknown"


def infer_speaker_type(parsed: dict[str, Any], transcript_text: str, source_type: str) -> str:
    hinted = model_hint(parsed["diagnostic_hints"], "speaker_type", SPEAKER_TYPE_VALUES)
    if hinted:
        return hinted

    if parsed["pass2"]["position_intelligence"] and parsed["pass2"]["gatekeeper_mentions"]:
        return "mixed"
    if parsed["pass2"]["position_intelligence"]:
        return "intermediary"
    if source_type == "operator_interview":
        return "operator"

    lowered = transcript_text.lower()
    if any(token in lowered for token in ("our platform", "our partners", "throughput high")):
        return "intermediary"
    if any(token in lowered for token in ("we paid", "we lost clients", "our workflow")):
        return "operator"
    return "unknown"


def infer_phase_fit(parsed: dict[str, Any]) -> str:
    hinted = model_hint(parsed["diagnostic_hints"], "phase_fit", PHASE_VALUES)
    if hinted:
        return hinted

    phases = set()
    if parsed["pass2"]["subniche_culture_signals"]:
        phases.add("0")
    if parsed["pass1"]["behavior_signals"] or parsed["pass1"]["opinion_signals"]:
        phases.add("1")
    if parsed["pass2"]["cascade_indicators"]:
        phases.add("2")
    if parsed["pass2"]["gatekeeper_mentions"]:
        phases.add("3")
    if parsed["pass2"]["position_intelligence"]:
        phases.add("3.5")

    if not phases:
        return "unknown"
    if len(phases) == 1:
        return next(iter(phases))
    return "mixed"


def infer_signal_density(parsed: dict[str, Any]) -> str:
    hinted = model_hint(parsed["diagnostic_hints"], "signal_density", SIGNAL_DENSITY_VALUES)
    if hinted:
        return hinted

    total_signals = sum(
        len(parsed["pass1"][key])
        for key in ("behavior_signals", "opinion_signals")
    ) + sum(
        len(parsed["pass2"][key])
        for key in (
            "cascade_indicators",
            "gatekeeper_mentions",
            "position_intelligence",
            "subniche_culture_signals",
        )
    )
    if total_signals >= 8:
        return "high"
    if total_signals >= 4:
        return "medium"
    return "low"


def derive_named_entities(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    hinted_entities = parsed["diagnostic_hints"].get("named_entities") or []
    normalized_entities = []

    for entity in hinted_entities:
        name = str(entity.get("name", "")).strip()
        if not name:
            continue
        normalized_entities.append(
            {
                "name": name,
                "entity_kind": normalize_entity_kind(entity.get("entity_kind"), name),
                "relationship": normalize_entity_relationship(entity.get("relationship")),
                "supporting_quote": str(entity.get("supporting_quote", "")).strip(),
                "confidence": normalize_confidence(entity.get("confidence"), "medium"),
            }
        )

    if normalized_entities:
        return normalized_entities

    derived = []
    for mention in parsed["pass2"]["gatekeeper_mentions"]:
        entity_name = str(mention.get("ENTITY NAMED", "")).strip()
        if not entity_name:
            continue
        derived.append(
            {
                "name": entity_name,
                "entity_kind": normalize_entity_kind(
                    mention.get("DEPENDENCY TYPE"),
                    entity_name,
                ),
                "relationship": normalize_entity_relationship(mention.get("OPERATOR RELATIONSHIP")),
                "supporting_quote": str(mention.get("QUOTE", "")).strip(),
                "confidence": "medium",
            }
        )
    return derived


def derive_gatekeepers(parsed: dict[str, Any], named_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hinted = parsed["diagnostic_hints"].get("gatekeepers") or []
    normalized_gatekeepers = []

    for gatekeeper in hinted:
        entity = str(gatekeeper.get("entity", "")).strip()
        if not entity:
            continue
        dependency_type = normalize_dependency_type(gatekeeper.get("dependency_type"))
        entity_kind = normalize_entity_kind("", entity)
        normalized_gatekeepers.append(
            {
                "entity": entity,
                "dependency_type": dependency_type,
                "gatekeeper_type": gatekeeper.get("gatekeeper_type")
                if gatekeeper.get("gatekeeper_type") in GATEKEEPER_TYPE_VALUES
                else infer_gatekeeper_type(dependency_type, entity_kind),
                "operator_relationship": normalize_gatekeeper_relationship(
                    gatekeeper.get("operator_relationship")
                ),
                "supporting_quote": str(gatekeeper.get("supporting_quote", "")).strip(),
                "confidence": normalize_confidence(gatekeeper.get("confidence"), "medium"),
            }
        )

    if normalized_gatekeepers:
        return normalized_gatekeepers

    named_entity_map = {entity["name"].lower(): entity for entity in named_entities}
    derived = []
    for mention in parsed["pass2"]["gatekeeper_mentions"]:
        entity_name = str(mention.get("ENTITY NAMED", "")).strip()
        if not entity_name:
            continue
        dependency_type = normalize_dependency_type(mention.get("DEPENDENCY TYPE"))
        entity_kind = named_entity_map.get(entity_name.lower(), {}).get(
            "entity_kind",
            normalize_entity_kind(mention.get("DEPENDENCY TYPE"), entity_name),
        )
        derived.append(
            {
                "entity": entity_name,
                "dependency_type": dependency_type,
                "gatekeeper_type": infer_gatekeeper_type(dependency_type, entity_kind),
                "operator_relationship": normalize_gatekeeper_relationship(
                    mention.get("OPERATOR RELATIONSHIP")
                ),
                "supporting_quote": str(mention.get("QUOTE", "")).strip(),
                "confidence": "medium",
            }
        )
    return derived


def derive_register_alignment(
    parsed: dict[str, Any],
    transcript_text: str,
    source_type: str,
    speaker_type: str,
) -> list[dict[str, Any]]:
    hinted = parsed["diagnostic_hints"].get("register_alignment") or []
    normalized_hint = []
    for item in hinted:
        register = str(item.get("register", "")).strip()
        if register not in REGISTER_NAMES:
            continue
        normalized_hint.append(
            {
                "register": register,
                "matched_signals": max(int(item.get("matched_signals", 0)), 0),
                "strength": str(item.get("strength", "low")).strip().lower(),
            }
        )
    if normalized_hint:
        return normalized_hint

    counts: defaultdict[str, int] = defaultdict(int)
    behavior_signals = parsed["pass1"]["behavior_signals"]
    opinion_signals = parsed["pass1"]["opinion_signals"]
    cascade_indicators = parsed["pass2"]["cascade_indicators"]
    gatekeeper_mentions = parsed["pass2"]["gatekeeper_mentions"]
    position_intelligence = parsed["pass2"]["position_intelligence"]
    culture_signals = parsed["pass2"]["subniche_culture_signals"]

    counts["operator_vernacular"] += len(behavior_signals) + len(culture_signals)
    counts["complaint_register"] += len(opinion_signals)
    counts["consequence_register"] += len(cascade_indicators)
    counts["intermediary_register"] += len(gatekeeper_mentions)

    if source_type in {"panel", "trade_discussion"}:
        counts["trade_publication"] += 1
    if source_type == "vendor_demo":
        counts["industry_professional"] += 1
    if speaker_type == "intermediary" and position_intelligence:
        counts["gatekeeper_self_description"] += len(position_intelligence)
    if position_intelligence:
        counts["industry_professional"] += len(position_intelligence)
    if re.search(r"\b20\d{2}\b", transcript_text) or "this year" in transcript_text.lower():
        counts["year_specific"] += 1
    if re.search(r"\b(job|hiring|responsibilities|requirements)\b", transcript_text.lower()):
        counts["job_listing_register"] += 1

    alignment = []
    for register in REGISTER_NAMES:
        matched_signals = counts.get(register, 0)
        if matched_signals <= 0:
            continue
        if matched_signals >= 3:
            strength = "high"
        elif matched_signals == 2:
            strength = "medium"
        else:
            strength = "low"
        alignment.append(
            {
                "register": register,
                "matched_signals": matched_signals,
                "strength": strength,
            }
        )
    return alignment


def extract_recommended_phase(next_action: str) -> str:
    # Prefer an explicit "Phase N"; a bare digit ("run 2 more interviews") is a guess.
    match = re.search(r"\bphase\s*(3\.5|[0-3])\b", next_action, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"\b(3\.5|0|1|2|3)\b", next_action)
    if match:
        return match.group(1)
    return "unknown"


def derive_search_language_feedback(
    provenance: dict[str, Any],
    source_type: str,
    speaker_type: str,
    phase_fit: str,
    signal_density: str,
) -> dict[str, Any]:
    query_used = str(provenance.get("query_used") or "").strip()
    query_lower = query_used.lower()

    likely_too_generic = False
    too_vendor_heavy = source_type == "vendor_demo"
    off_phase = False
    likely_operator_facing = speaker_type in {"operator", "mixed"}
    likely_gatekeeper_facing = speaker_type == "intermediary"

    reasons = []

    if not query_used:
        reasons.append("No query metadata was provided for this source.")
    else:
        matched_generic_terms = [term for term in GENERIC_QUERY_TERMS if term in query_lower]
        if matched_generic_terms and signal_density == "low":
            likely_too_generic = True
            reasons.append(
                f"Query used broad language ({', '.join(sorted(matched_generic_terms))}) and produced low signal density."
            )

        if any(term in query_lower for term in ("vendor", "demo", "platform overview")):
            too_vendor_heavy = True
            reasons.append("Query language appears vendor-facing or demo-oriented.")

    if phase_fit in {"3", "3.5"} and likely_operator_facing:
        off_phase = True
        reasons.append("Signals skew operator-facing while the extracted fit is gatekeeper-oriented.")
    elif phase_fit in {"0", "1", "2"} and likely_gatekeeper_facing:
        off_phase = True
        reasons.append("Signals skew gatekeeper-facing while the extracted fit leans operator-oriented.")

    if not reasons:
        reasons.append("Heuristic review found no strong search-language issues.")

    return {
        "likely_too_generic": likely_too_generic,
        "too_vendor_heavy": too_vendor_heavy,
        "off_phase": off_phase,
        "likely_operator_facing": likely_operator_facing,
        "likely_gatekeeper_facing": likely_gatekeeper_facing,
        "reason": " ".join(reasons),
    }


def build_diagnostics(parsed: dict[str, Any], transcript_text: str, provenance: dict[str, Any]) -> dict[str, Any]:
    source_type = infer_source_type(transcript_text, parsed["diagnostic_hints"])
    speaker_type = infer_speaker_type(parsed, transcript_text, source_type)
    phase_fit = infer_phase_fit(parsed)
    signal_density = infer_signal_density(parsed)
    named_entities = derive_named_entities(parsed)
    gatekeepers = derive_gatekeepers(parsed, named_entities)
    register_alignment = derive_register_alignment(parsed, transcript_text, source_type, speaker_type)
    search_language_feedback = derive_search_language_feedback(
        provenance,
        source_type,
        speaker_type,
        phase_fit,
        signal_density,
    )
    recommended_next_phase = extract_recommended_phase(
        parsed["pass2"]["summary"].get("recommended_next_action", "")
    )
    phase_from_model = recommended_next_phase != "unknown"
    diagnostic_notes = list(parsed["diagnostic_hints"].get("diagnostic_notes") or [])

    if gatekeepers and recommended_next_phase == "unknown":
        recommended_next_phase = "3"
    if parsed["pass2"]["position_intelligence"] and recommended_next_phase == "unknown":
        recommended_next_phase = "3.5"
    if parsed["pass2"]["cascade_indicators"] and recommended_next_phase == "unknown":
        recommended_next_phase = "2"
    if parsed["pass2"]["subniche_culture_signals"] and recommended_next_phase == "unknown":
        recommended_next_phase = "0"
    if parsed["pass1"]["behavior_signals"] and recommended_next_phase == "unknown":
        recommended_next_phase = "1"

    hints = parsed["diagnostic_hints"]

    def origin(key: str, allowed: set[str], value: str, empty: str = "unknown") -> str:
        if model_hint(hints, key, allowed):
            return "llm"
        return "default" if value == empty else "heuristic"

    def list_origin(key: str, value: list) -> str:
        if hints.get(key) and value:
            return "llm" if any(v for v in hints[key]) else "heuristic"
        return "heuristic" if value else "default"

    # Which values the model stated and which this module inferred. An agent
    # should weigh a heuristic guess below the model's direct answer.
    field_sources = {
        "source_type": origin("source_type", SOURCE_TYPE_VALUES, source_type),
        "speaker_type": origin("speaker_type", SPEAKER_TYPE_VALUES, speaker_type),
        "phase_fit": origin("phase_fit", PHASE_VALUES, phase_fit),
        "signal_density": origin("signal_density", SIGNAL_DENSITY_VALUES, signal_density, empty=""),
        "named_entities": list_origin("named_entities", named_entities),
        "gatekeepers": list_origin("gatekeepers", gatekeepers),
        "register_alignment": list_origin("register_alignment", register_alignment),
        "recommended_next_phase": "llm" if phase_from_model
        else ("default" if recommended_next_phase == "unknown" else "heuristic"),
    }

    return {
        "field_sources": field_sources,
        "phase_fit": phase_fit,
        "signal_density": signal_density,
        "register_alignment": register_alignment,
        "named_entities": named_entities,
        "gatekeepers": gatekeepers,
        "search_language_feedback": search_language_feedback,
        "recommended_next_phase": recommended_next_phase,
        "diagnostic_notes": diagnostic_notes,
        "source_type": source_type,
        "speaker_type": speaker_type,
    }


def aggregate_named_entities(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], dict[str, Any]] = {}
    for result in results:
        for entity in result["diagnostics"]["named_entities"]:
            key = (entity["name"].lower(), entity["entity_kind"])
            bucket = counts.setdefault(
                key,
                {
                    "name": entity["name"],
                    "entity_kind": entity["entity_kind"],
                    "count": 0,
                    "source_ids": [],
                },
            )
            bucket["count"] += 1
            bucket["source_ids"].append(result["source"]["source_id"])
    recurring = list(counts.values())
    recurring.sort(key=lambda item: (-item["count"], item["name"].lower()))
    return recurring


def most_common_phase(results: list[dict[str, Any]]) -> str:
    counter = Counter(result["diagnostics"]["recommended_next_phase"] for result in results)
    if not counter:
        return "unknown"
    phase, _ = counter.most_common(1)[0]
    return phase
