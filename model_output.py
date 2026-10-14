"""The model's output contract: a JSON Schema the provider enforces at decode time,
and an adapter from that JSON to the internal `parsed` dict that diagnostics.py,
verify.py and render.py already consume.

Older runs stored plain text; `parse_any` still routes those to extract.py so
saved results can be replayed.
"""
from __future__ import annotations

import json
from typing import Any

from extract import parse_model_output as parse_legacy_text
from schemas import REGISTER_NAMES
from retry import MalformedModelOutput

CONF = ["Low", "Medium", "High"]
conf_lower = ["low", "medium", "high"]


def obj(**props: Any) -> dict[str, Any]:
    """Strict object: every property required, nothing extra. OpenAI strict mode
    demands this; Gemini accepts it."""
    return {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}


def arr(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


def enum(*values: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


S = {"type": "string"}
QUOTE = {"type": "string", "description": "One continuous span copied verbatim from the transcript. "
                                          "Never join separate sentences; make two signals instead."}

MODEL_OUTPUT_SCHEMA = obj(
    behavior_signals=arr(obj(
        quote=QUOTE,
        category=enum("Money Spent", "Tool Abandoned", "Active Workaround", "Urgency-Consequence"),
        wtp_implication=S)),
    opinion_signals=arr(obj(quote=QUOTE, why_low_signal=S)),
    pass1_summary=obj(total_high_signal_moments={"type": "integer"},
                      dominant_pain_category=S, confidence_level=enum(*CONF)),
    cascade_indicators=arr(obj(
        quote=QUOTE, layers_broken=S,
        cascade_depth=enum("Single-layer", "Two-layer", "Three-layer+"), build_signal=S)),
    gatekeeper_mentions=arr(obj(
        quote=QUOTE, entity_named=S,
        dependency_type=enum("Structural Friction", "Social Authority", "Information Asymmetry", "Platform"),
        operator_relationship=enum("Dependent", "Frustrated", "Loyal", "Switching away"),
        gatekeeper_signal=S)),
    position_intelligence=arr(obj(quote=QUOTE, entity=S, what_they_protect=S, confidence=enum(*CONF))),
    subniche_culture_signals=arr(obj(
        quote=QUOTE, subniche_identified=S, differentiation_claim=S,
        fgp_use=enum("Phase 0 frame sharpening", "Phase 3.5 positioning context", "Both"))),
    pass2_summary=obj(strongest_cascade_found=S, highest_signal_gatekeeper_mention=S,
                      position_intelligence_confidence=enum(*CONF), recommended_next_action=S),
    top_3_actionable_signals=arr(S),
    hypothesis_worth_testing=S,
    source_diagnostics=obj(
        source_type=enum("operator_interview", "panel", "vendor_demo", "trade_discussion", "unknown"),
        speaker_type=enum("operator", "intermediary", "mixed", "unknown"),
        phase_fit=enum("0", "1", "2", "3", "3.5", "mixed", "unknown"),
        signal_density=enum(*conf_lower)),
    named_entities=arr(obj(
        name=S,
        entity_kind=enum("platform", "software", "institution", "distributor", "person",
                         "certification_body", "other"),
        relationship=enum("dependent", "frustrated", "switching", "praise", "unknown"),
        supporting_quote=QUOTE, confidence=enum(*conf_lower))),
    gatekeeper_objects=arr(obj(
        entity=S,
        dependency_type=enum("structural_friction", "social_authority", "information_asymmetry",
                             "platform", "unknown"),
        gatekeeper_type=enum("Type1", "Type2", "Type3", "Type4", "unknown"),
        operator_relationship=enum("dependent", "frustrated", "loyal", "switching_away", "unknown"),
        supporting_quote=QUOTE, confidence=enum(*conf_lower))),
    register_alignment=arr(obj(register=enum(*REGISTER_NAMES), matched_signals={"type": "integer"},
                               strength=enum(*conf_lower))),
    search_language_feedback=obj(likely_too_generic={"type": "boolean"},
                                 too_vendor_heavy={"type": "boolean"},
                                 off_phase={"type": "boolean"},
                                 likely_operator_facing={"type": "boolean"},
                                 likely_gatekeeper_facing={"type": "boolean"},
                                 reason=S),
    diagnostic_notes=arr(S),
)

# JSON field -> the UPPERCASE label the legacy text format used. Internal code
# and saved results keep these labels, so the result JSON shape is unchanged.
LABELS = {
    "quote": "QUOTE", "category": "CATEGORY", "wtp_implication": "WTP IMPLICATION",
    "why_low_signal": "WHY LOW SIGNAL", "layers_broken": "LAYERS BROKEN",
    "cascade_depth": "CASCADE DEPTH", "build_signal": "BUILD SIGNAL",
    "entity_named": "ENTITY NAMED", "dependency_type": "DEPENDENCY TYPE",
    "operator_relationship": "OPERATOR RELATIONSHIP", "gatekeeper_signal": "GATEKEEPER SIGNAL",
    "entity": "ENTITY", "what_they_protect": "WHAT THEY PROTECT", "confidence": "CONFIDENCE",
    "subniche_identified": "SUBNICHE IDENTIFIED", "differentiation_claim": "DIFFERENTIATION CLAIM",
    "fgp_use": "FGP USE",
}


def safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def labelled(items: Any) -> list[dict[str, str]]:
    return [{LABELS.get(k, k.upper()): str(v) for k, v in item.items()}
            for item in (items or []) if isinstance(item, dict)]


def load_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):                       # tolerate a fenced reply
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise MalformedModelOutput(f"Model output is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise MalformedModelOutput("Model output JSON is not an object.")
    return data


def schema_errors(schema: dict[str, Any], value: Any, path: str = "$", limit: int = 20) -> list[str]:
    """Check value against the subset of JSON Schema used above. Servers that only
    promise "some JSON" (json_object mode) are held to the schema here."""
    errors: list[str] = []

    def walk(node: dict[str, Any], v: Any, p: str) -> None:
        if len(errors) >= limit:
            return
        kind = node.get("type")
        if kind == "object":
            if not isinstance(v, dict):
                errors.append(f"{p}: expected object")
                return
            for key in node.get("required", []):
                if key not in v:
                    errors.append(f"{p}.{key}: missing")
            for key, item in v.items():
                if key in node["properties"]:
                    walk(node["properties"][key], item, f"{p}.{key}")
                elif node.get("additionalProperties") is False:
                    errors.append(f"{p}.{key}: unexpected field")
        elif kind == "array":
            if not isinstance(v, list):
                errors.append(f"{p}: expected array")
                return
            for i, item in enumerate(v):
                walk(node["items"], item, f"{p}[{i}]")
        elif kind == "string":
            if not isinstance(v, str):
                errors.append(f"{p}: expected string")
            elif "enum" in node and v not in node["enum"]:
                errors.append(f"{p}: {v!r} not one of {node['enum']}")
        elif kind == "integer" and (not isinstance(v, int) or isinstance(v, bool)):
            errors.append(f"{p}: expected integer")
        elif kind == "boolean" and not isinstance(v, bool):
            errors.append(f"{p}: expected boolean")

    walk(schema, value, path)
    return errors


def parse_structured_output(raw: str) -> dict[str, Any]:
    data = load_json(raw)
    warnings = [f"Model JSON violates schema at {e}" for e in schema_errors(MODEL_OUTPUT_SCHEMA, data)]

    behavior = labelled(data.get("behavior_signals"))
    p1 = data.get("pass1_summary") or {}
    p2 = data.get("pass2_summary") or {}
    diag = data.get("source_diagnostics") or {}
    feedback = data.get("search_language_feedback") or {}

    return {
        "pass1": {
            "behavior_signals": behavior,
            "opinion_signals": labelled(data.get("opinion_signals")),
            "summary": {
                "total_high_signal_moments": safe_int(p1.get("total_high_signal_moments"), len(behavior)),
                "dominant_pain_category": p1.get("dominant_pain_category") or "None found.",
                "confidence_level": p1.get("confidence_level") or "Not provided.",
            },
        },
        "pass2": {
            "cascade_indicators": labelled(data.get("cascade_indicators")),
            "gatekeeper_mentions": labelled(data.get("gatekeeper_mentions")),
            "position_intelligence": labelled(data.get("position_intelligence")),
            "subniche_culture_signals": labelled(data.get("subniche_culture_signals")),
            "summary": {
                "strongest_cascade_found": p2.get("strongest_cascade_found") or "None found.",
                "highest_signal_gatekeeper_mention": p2.get("highest_signal_gatekeeper_mention") or "None found.",
                "position_intelligence_confidence": str(p2.get("position_intelligence_confidence") or "low").lower(),
                "recommended_next_action": p2.get("recommended_next_action") or "Not provided.",
            },
        },
        "combined_summary": {
            "top_3_actionable_signals": [str(s) for s in (data.get("top_3_actionable_signals") or [])][:3],
            "hypothesis_worth_testing": data.get("hypothesis_worth_testing") or "None found.",
        },
        "diagnostic_hints": {
            "source_type": diag.get("source_type"),
            "speaker_type": diag.get("speaker_type"),
            "phase_fit": diag.get("phase_fit"),
            "signal_density": diag.get("signal_density"),
            "named_entities": list(data.get("named_entities") or []),
            "gatekeepers": list(data.get("gatekeeper_objects") or []),
            "register_alignment": list(data.get("register_alignment") or []),
            "search_language_feedback": {
                key: bool(feedback.get(key, False))
                for key in ("likely_too_generic", "too_vendor_heavy", "off_phase",
                            "likely_operator_facing", "likely_gatekeeper_facing")
            } | {"reason": feedback.get("reason") or "Not provided."},
            "diagnostic_notes": [str(n) for n in (data.get("diagnostic_notes") or [])],
        },
        "parse_warnings": warnings,
        "raw_output": raw,
    }


def parse_any(raw: str) -> tuple[dict[str, Any], str]:
    """(parsed, output_format). JSON from current runs; plain text from older ones."""
    if raw.lstrip().startswith(("{", "```")):
        return parse_structured_output(raw), "json"
    return parse_legacy_text(raw), "legacy_text"
