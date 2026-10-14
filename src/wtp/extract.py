from __future__ import annotations

import re
from collections import Counter
from typing import Any


SECTION_PATTERNS = [
    ("behavior", r"BEHAVIOR[- ]LEVEL SIGNALS"),
    ("opinion", r"OPINION[- ]LEVEL SIGNALS"),
    ("pass1_summary", r"PASS 1 SUMMARY"),
    ("pass2_title", r"PASS 2:\s*FGP PIPELINE INTELLIGENCE"),
    ("category_a", r"CATEGORY A\s*[—-]\s*CASCADE INDICATORS"),
    ("category_b", r"CATEGORY B\s*[—-]\s*GATEKEEPER MENTIONS"),
    ("category_c", r"CATEGORY C\s*[—-]\s*POSITION INTELLIGENCE"),
    ("category_d", r"CATEGORY D\s*[—-]\s*SUBNICHE CULTURE SIGNALS"),
    ("pass2_summary", r"PASS 2 SUMMARY"),
    ("combined_summary", r"COMBINED INTELLIGENCE SUMMARY"),
    ("top3", r"TOP 3 ACTIONABLE SIGNALS ACROSS BOTH PASSES:?"),
    ("hypothesis", r"ONE HYPOTHESIS WORTH TESTING:?"),
    ("source_diagnostics", r"SOURCE DIAGNOSTICS"),
    ("named_entities", r"NAMED ENTITIES"),
    ("gatekeeper_objects", r"GATEKEEPER OBJECTS"),
    ("register_alignment", r"REGISTER ALIGNMENT"),
    ("search_language_feedback", r"SEARCH LANGUAGE FEEDBACK"),
    ("diagnostic_notes", r"DIAGNOSTIC NOTES"),
]

PASS1_SUMMARY_FIELDS = {
    "TOTAL HIGH-SIGNAL MOMENTS": "total_high_signal_moments",
    "DOMINANT PAIN CATEGORY": "dominant_pain_category",
    "CONFIDENCE LEVEL": "confidence_level",
}

PASS2_SUMMARY_FIELDS = {
    "STRONGEST CASCADE FOUND": "strongest_cascade_found",
    "HIGHEST-SIGNAL GATEKEEPER MENTION": "highest_signal_gatekeeper_mention",
    "POSITION INTELLIGENCE CONFIDENCE": "position_intelligence_confidence",
    "RECOMMENDED NEXT ACTION": "recommended_next_action",
}

SOURCE_DIAGNOSTIC_FIELDS = {
    "SOURCE TYPE": "source_type",
    "SPEAKER TYPE": "speaker_type",
    "PHASE FIT": "phase_fit",
    "SIGNAL DENSITY": "signal_density",
}

SEARCH_LANGUAGE_FIELDS = {
    "LIKELY TOO GENERIC": "likely_too_generic",
    "TOO VENDOR HEAVY": "too_vendor_heavy",
    "OFF PHASE": "off_phase",
    "LIKELY OPERATOR FACING": "likely_operator_facing",
    "LIKELY GATEKEEPER FACING": "likely_gatekeeper_facing",
    "REASON": "reason",
}


def clean_model_output(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[*`]+", "", text)
    return text


def is_decorative_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return all(character in "═=-_~#·.?" for character in stripped)


def get_section_bounds(text: str) -> dict[str, tuple[int, int]]:
    found_sections = []
    for key, pattern in SECTION_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            found_sections.append((match.start(), match.end(), key))

    found_sections.sort()
    bounds: dict[str, tuple[int, int]] = {}
    for index, (start, end, key) in enumerate(found_sections):
        next_start = found_sections[index + 1][0] if index + 1 < len(found_sections) else len(text)
        bounds[key] = (end, next_start)
    return bounds


def extract_section_text(text: str, bounds: dict[str, tuple[int, int]], key: str) -> str:
    if key not in bounds:
        return ""
    start, end = bounds[key]
    return text[start:end].strip()


def parse_labeled_blocks(section_text: str, expected_fields: list[str]) -> list[dict[str, str]]:
    expected = {field.upper(): field for field in expected_fields}
    blocks: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    active_field: str | None = None

    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line or line == "---" or line.lower() == "none found." or is_decorative_line(line):
            continue

        line = re.sub(r"^[\-\d\.\)\s]+", "", line)
        match = re.match(r"([A-Z][A-Z0-9 /\-\+]+):\s*(.*)$", line)

        if match:
            label = match.group(1).strip().upper()
            value = match.group(2).strip()
            if label in expected:
                canonical = expected[label]
                # A label seen twice means a new record. (Starting a record on
                # fixed labels like ENTITY split every position_intelligence
                # signal, where ENTITY follows QUOTE, into two halves.)
                if current is not None and canonical in current:
                    blocks.append(current)
                    current = {}
                if current is None:
                    current = {}
                current[canonical] = value
                active_field = canonical
                continue

        if current is not None and active_field:
            current[active_field] = f"{current[active_field]} {line}".strip()

    if current:
        blocks.append(current)

    return blocks


def parse_key_value_lines(section_text: str, field_map: dict[str, str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    active_key: str | None = None

    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line or line == "---" or is_decorative_line(line):
            continue

        line = re.sub(r"^[\-\d\.\)\s]+", "", line)
        match = re.match(r"([A-Z][A-Z0-9 /\-\+]+):\s*(.*)$", line, flags=re.IGNORECASE)
        if match:
            label = match.group(1).strip().upper()
            value = match.group(2).strip()
            if label in field_map:
                active_key = field_map[label]
                parsed[active_key] = value
                continue

        if active_key:
            parsed[active_key] = f"{parsed[active_key]} {line}".strip()

    return parsed


def parse_numbered_items(section_text: str) -> list[str]:
    items: list[str] = []
    current: str | None = None

    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line or line == "---" or is_decorative_line(line):
            continue

        match = re.match(r"(\d+)\.\s*(.*)$", line)
        if match:
            if current is not None:
                items.append(current.strip())
            current = match.group(2).strip()
            continue

        if current is not None:
            current = f"{current} {line}".strip()

    if current is not None:
        items.append(current.strip())

    return items


def extract_freeform_text(section_text: str) -> str:
    lines = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line or line == "---" or is_decorative_line(line):
            continue
        line = re.sub(r"^[\-\d\.\)\s]+", "", line)
        lines.append(line)
    return " ".join(lines).strip()


def parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"true", "yes", "y"}


def parse_int(value: str | None, fallback: int = 0) -> int:
    if value is None:
        return fallback
    match = re.search(r"\d+", value)
    if not match:
        return fallback
    return int(match.group(0))


def most_common_behavior_category(signals: list[dict[str, str]]) -> str:
    categories = [signal.get("CATEGORY", "").strip() for signal in signals if signal.get("CATEGORY")]
    if not categories:
        return "None found."
    return Counter(categories).most_common(1)[0][0]


def cascade_depth_rank(depth: str) -> int:
    normalized = depth.strip().lower()
    if "three-layer" in normalized:
        return 3
    if "two-layer" in normalized:
        return 2
    if "single-layer" in normalized:
        return 1
    return 0


def strongest_cascade(signals: list[dict[str, str]]) -> str:
    if not signals:
        return "None found."
    signal = max(signals, key=lambda item: cascade_depth_rank(item.get("CASCADE DEPTH", "")))
    return f"{signal.get('QUOTE', 'Not provided.')} ({signal.get('CASCADE DEPTH', 'Not provided.')})"


def highest_signal_gatekeeper(signals: list[dict[str, str]]) -> str:
    if not signals:
        return "None found."
    signal = signals[0]
    return (
        f"{signal.get('ENTITY NAMED', 'Not provided.')} "
        f"({signal.get('DEPENDENCY TYPE', 'Not provided.')})"
    )


def infer_position_intelligence_confidence(signals: list[dict[str, str]]) -> str:
    if not signals:
        return "low"

    normalized = [signal.get("CONFIDENCE", "").strip().lower() for signal in signals]
    if normalized and all(value == "high" for value in normalized if value):
        return "high"
    if any(value in {"high", "medium"} for value in normalized):
        return "medium"
    return "low"


def normalize_named_entity_blocks(blocks: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = []
    for block in blocks:
        normalized.append(
            {
                "name": block.get("NAME", ""),
                "entity_kind": block.get("ENTITY KIND", "other"),
                "relationship": block.get("RELATIONSHIP", "unknown"),
                "supporting_quote": block.get("SUPPORTING QUOTE", ""),
                "confidence": block.get("CONFIDENCE", "low"),
            }
        )
    return normalized


def normalize_gatekeeper_blocks(blocks: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = []
    for block in blocks:
        normalized.append(
            {
                "entity": block.get("ENTITY", ""),
                "dependency_type": block.get("DEPENDENCY TYPE", "unknown"),
                "gatekeeper_type": block.get("GATEKEEPER TYPE", "unknown"),
                "operator_relationship": block.get("OPERATOR RELATIONSHIP", "unknown"),
                "supporting_quote": block.get("SUPPORTING QUOTE", ""),
                "confidence": block.get("CONFIDENCE", "low"),
            }
        )
    return normalized


def normalize_register_blocks(blocks: list[dict[str, str]]) -> list[dict[str, Any]]:
    normalized = []
    for block in blocks:
        normalized.append(
            {
                "register": block.get("REGISTER", ""),
                "matched_signals": parse_int(block.get("MATCHED SIGNALS"), 0),
                "strength": block.get("STRENGTH", "low"),
            }
        )
    return normalized


def parse_model_output(raw_output: str) -> dict[str, Any]:
    text = clean_model_output(raw_output)
    bounds = get_section_bounds(text)
    parse_warnings: list[str] = []

    behavior_signals = parse_labeled_blocks(
        extract_section_text(text, bounds, "behavior"),
        ["QUOTE", "CATEGORY", "WTP IMPLICATION"],
    )
    opinion_signals = parse_labeled_blocks(
        extract_section_text(text, bounds, "opinion"),
        ["QUOTE", "WHY LOW SIGNAL"],
    )
    pass1_summary = parse_key_value_lines(
        extract_section_text(text, bounds, "pass1_summary"),
        PASS1_SUMMARY_FIELDS,
    )

    cascade_indicators = parse_labeled_blocks(
        extract_section_text(text, bounds, "category_a"),
        ["QUOTE", "LAYERS BROKEN", "CASCADE DEPTH", "BUILD SIGNAL"],
    )
    gatekeeper_mentions = parse_labeled_blocks(
        extract_section_text(text, bounds, "category_b"),
        [
            "QUOTE",
            "ENTITY NAMED",
            "DEPENDENCY TYPE",
            "OPERATOR RELATIONSHIP",
            "GATEKEEPER SIGNAL",
        ],
    )
    position_intelligence = parse_labeled_blocks(
        extract_section_text(text, bounds, "category_c"),
        ["QUOTE", "ENTITY", "WHAT THEY PROTECT", "CONFIDENCE"],
    )
    subniche_culture_signals = parse_labeled_blocks(
        extract_section_text(text, bounds, "category_d"),
        ["QUOTE", "SUBNICHE IDENTIFIED", "DIFFERENTIATION CLAIM", "FGP USE"],
    )
    pass2_summary = parse_key_value_lines(
        extract_section_text(text, bounds, "pass2_summary"),
        PASS2_SUMMARY_FIELDS,
    )

    top_three_signals = parse_numbered_items(extract_section_text(text, bounds, "top3"))
    hypothesis = extract_freeform_text(extract_section_text(text, bounds, "hypothesis")) or "None found."

    source_diagnostics = parse_key_value_lines(
        extract_section_text(text, bounds, "source_diagnostics"),
        SOURCE_DIAGNOSTIC_FIELDS,
    )
    search_language_feedback = parse_key_value_lines(
        extract_section_text(text, bounds, "search_language_feedback"),
        SEARCH_LANGUAGE_FIELDS,
    )
    named_entities = normalize_named_entity_blocks(
        parse_labeled_blocks(
            extract_section_text(text, bounds, "named_entities"),
            ["NAME", "ENTITY KIND", "RELATIONSHIP", "SUPPORTING QUOTE", "CONFIDENCE"],
        )
    )
    gatekeeper_objects = normalize_gatekeeper_blocks(
        parse_labeled_blocks(
            extract_section_text(text, bounds, "gatekeeper_objects"),
            [
                "ENTITY",
                "DEPENDENCY TYPE",
                "GATEKEEPER TYPE",
                "OPERATOR RELATIONSHIP",
                "SUPPORTING QUOTE",
                "CONFIDENCE",
            ],
        )
    )
    register_alignment = normalize_register_blocks(
        parse_labeled_blocks(
            extract_section_text(text, bounds, "register_alignment"),
            ["REGISTER", "MATCHED SIGNALS", "STRENGTH"],
        )
    )
    diagnostic_notes = parse_numbered_items(extract_section_text(text, bounds, "diagnostic_notes"))

    if "behavior" not in bounds:
        parse_warnings.append("Missing BEHAVIOR-LEVEL SIGNALS section in model output.")
    if "category_b" not in bounds:
        parse_warnings.append("Missing CATEGORY B gatekeeper section in model output.")
    if not top_three_signals:
        parse_warnings.append("Missing or empty TOP 3 ACTIONABLE SIGNALS section in model output.")

    return {
        "pass1": {
            "behavior_signals": behavior_signals,
            "opinion_signals": opinion_signals,
            "summary": {
                "total_high_signal_moments": parse_int(
                    pass1_summary.get("total_high_signal_moments"),
                    len(behavior_signals),
                ),
                "dominant_pain_category": pass1_summary.get("dominant_pain_category")
                or most_common_behavior_category(behavior_signals),
                "confidence_level": pass1_summary.get("confidence_level") or "Not provided.",
            },
        },
        "pass2": {
            "cascade_indicators": cascade_indicators,
            "gatekeeper_mentions": gatekeeper_mentions,
            "position_intelligence": position_intelligence,
            "subniche_culture_signals": subniche_culture_signals,
            "summary": {
                "strongest_cascade_found": pass2_summary.get("strongest_cascade_found")
                or strongest_cascade(cascade_indicators),
                "highest_signal_gatekeeper_mention": pass2_summary.get("highest_signal_gatekeeper_mention")
                or highest_signal_gatekeeper(gatekeeper_mentions),
                "position_intelligence_confidence": (
                    pass2_summary.get("position_intelligence_confidence")
                    or infer_position_intelligence_confidence(position_intelligence)
                ),
                "recommended_next_action": pass2_summary.get("recommended_next_action")
                or "Not provided.",
            },
        },
        "combined_summary": {
            "top_3_actionable_signals": top_three_signals[:3],
            "hypothesis_worth_testing": hypothesis,
        },
        "diagnostic_hints": {
            # None when the model gave nothing, so diagnostics.py can tell a
            # real answer from a missing one and fall back to its heuristics.
            "source_type": source_diagnostics.get("source_type"),
            "speaker_type": source_diagnostics.get("speaker_type"),
            "phase_fit": source_diagnostics.get("phase_fit"),
            "signal_density": source_diagnostics.get("signal_density"),
            "named_entities": named_entities,
            "gatekeepers": gatekeeper_objects,
            "register_alignment": register_alignment,
            "search_language_feedback": {
                "likely_too_generic": parse_bool(search_language_feedback.get("likely_too_generic")),
                "too_vendor_heavy": parse_bool(search_language_feedback.get("too_vendor_heavy")),
                "off_phase": parse_bool(search_language_feedback.get("off_phase")),
                "likely_operator_facing": parse_bool(
                    search_language_feedback.get("likely_operator_facing")
                ),
                "likely_gatekeeper_facing": parse_bool(
                    search_language_feedback.get("likely_gatekeeper_facing")
                ),
                "reason": search_language_feedback.get("reason", "Not provided."),
            },
            "diagnostic_notes": diagnostic_notes,
        },
        "parse_warnings": parse_warnings,
        "raw_output": raw_output,
    }
