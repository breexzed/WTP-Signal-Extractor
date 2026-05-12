from __future__ import annotations

import sys
from typing import Any


def safe_console_text(text: str) -> str:
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2192": "->",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u00a0": " ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)

    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding)


def render_signal_blocks(signals: list[dict[str, Any]], fields: list[str]) -> str:
    if not signals:
        return "None found."

    rendered = []
    for signal in signals:
        block = []
        for field in fields:
            value = signal.get(field) or "Not provided."
            block.append(f"- {field}: {value}")
        rendered.append("\n".join(block))
    return "\n\n".join(rendered)


def render_named_entities(entities: list[dict[str, Any]]) -> str:
    if not entities:
        return "None found."

    rendered = []
    for entity in entities:
        rendered.append(
            "\n".join(
                [
                    f"- NAME: {entity.get('name', 'Not provided.')}",
                    f"- ENTITY KIND: {entity.get('entity_kind', 'Not provided.')}",
                    f"- RELATIONSHIP: {entity.get('relationship', 'Not provided.')}",
                    f"- SUPPORTING QUOTE: {entity.get('supporting_quote', 'Not provided.')}",
                    f"- CONFIDENCE: {entity.get('confidence', 'Not provided.')}",
                ]
            )
        )
    return "\n\n".join(rendered)


def render_gatekeepers(gatekeepers: list[dict[str, Any]]) -> str:
    if not gatekeepers:
        return "None found."

    rendered = []
    for gatekeeper in gatekeepers:
        rendered.append(
            "\n".join(
                [
                    f"- ENTITY: {gatekeeper.get('entity', 'Not provided.')}",
                    f"- DEPENDENCY TYPE: {gatekeeper.get('dependency_type', 'Not provided.')}",
                    f"- GATEKEEPER TYPE: {gatekeeper.get('gatekeeper_type', 'Not provided.')}",
                    f"- OPERATOR RELATIONSHIP: {gatekeeper.get('operator_relationship', 'Not provided.')}",
                    f"- SUPPORTING QUOTE: {gatekeeper.get('supporting_quote', 'Not provided.')}",
                    f"- CONFIDENCE: {gatekeeper.get('confidence', 'Not provided.')}",
                ]
            )
        )
    return "\n\n".join(rendered)


def render_register_alignment(register_alignment: list[dict[str, Any]]) -> str:
    if not register_alignment:
        return "None found."

    rendered = []
    for item in register_alignment:
        rendered.append(
            "\n".join(
                [
                    f"- REGISTER: {item.get('register', 'Not provided.')}",
                    f"- MATCHED SIGNALS: {item.get('matched_signals', 0)}",
                    f"- STRENGTH: {item.get('strength', 'Not provided.')}",
                ]
            )
        )
    return "\n\n".join(rendered)


def render_parse_warnings(parse_warnings: list[str]) -> str:
    if not parse_warnings:
        return "None found."
    return "\n".join(f"- {warning}" for warning in parse_warnings)


def render_top_signals(items: list[str]) -> str:
    normalized = list(items[:3])
    while len(normalized) < 3:
        normalized.append("None found.")
    return "\n".join(f"{index}. {item}" for index, item in enumerate(normalized, start=1))


def render_session_sources(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "None found."

    rendered = []
    for source in sources:
        rendered.append(
            "\n".join(
                [
                    f"- SOURCE ID: {source.get('source_id', 'Not provided.')}",
                    f"- INPUT TYPE: {source.get('input_type', 'Not provided.')}",
                    f"- TRANSCRIPT STATUS: {source.get('transcript_status', 'Not provided.')}",
                    f"- SOURCE TYPE: {source.get('source_type', 'Not provided.')}",
                    f"- SPEAKER TYPE: {source.get('speaker_type', 'Not provided.')}",
                    f"- URL: {source.get('url') or 'None'}",
                ]
            )
        )
    return "\n\n".join(rendered)


def render_count_blocks(items: list[dict[str, Any]], label_field: str, value_field: str) -> str:
    if not items:
        return "None found."
    return "\n".join(
        f"- {item.get(label_field, 'Not provided.')}: {item.get(value_field, 0)}"
        for item in items
    )


def render_recurring_entities(items: list[dict[str, Any]]) -> str:
    if not items:
        return "None found."

    rendered = []
    for item in items:
        rendered.append(
            "\n".join(
                [
                    f"- NAME: {item.get('name', 'Not provided.')}",
                    f"- ENTITY KIND: {item.get('entity_kind', 'Not provided.')}",
                    f"- COUNT: {item.get('count', 0)}",
                    f"- SOURCE IDS: {', '.join(item.get('source_ids', [])) or 'None'}",
                ]
            )
        )
    return "\n\n".join(rendered)


def render_query_feedback(items: list[dict[str, Any]]) -> str:
    if not items:
        return "None found."

    rendered = []
    for item in items:
        rendered.append(
            "\n".join(
                [
                    f"- SOURCE ID: {item.get('source_id', 'Not provided.')}",
                    f"- QUERY USED: {item.get('query_used') or 'None'}",
                    f"- LIKELY TOO GENERIC: {item.get('likely_too_generic', False)}",
                    f"- TOO VENDOR HEAVY: {item.get('too_vendor_heavy', False)}",
                    f"- OFF PHASE: {item.get('off_phase', False)}",
                    f"- LIKELY OPERATOR FACING: {item.get('likely_operator_facing', False)}",
                    f"- LIKELY GATEKEEPER FACING: {item.get('likely_gatekeeper_facing', False)}",
                    f"- REASON: {item.get('reason', 'Not provided.')}",
                ]
            )
        )
    return "\n\n".join(rendered)


def render_session_context(session_context: dict[str, Any]) -> str:
    if not session_context:
        return "None provided."

    ordered_fields = [
        "vertical",
        "operator_type",
        "targeted_subniche",
        "fgp_phase",
        "gatekeeper_type",
        "currency_window",
        "session_date",
        "prior_loop_map_phase",
    ]
    rendered = []
    for field in ordered_fields:
        rendered.append(f"- {field.replace('_', ' ').title()}: {session_context.get(field) or 'None'}")
    return "\n".join(rendered)


def render_result(result: dict[str, Any]) -> str:
    source = result["source"]
    provenance = result["provenance"]
    diagnostics = result["diagnostics"]
    pass1 = result["pass1"]
    pass2 = result["pass2"]
    combined = result["combined_summary"]

    search_feedback = diagnostics["search_language_feedback"]
    diagnostic_notes = diagnostics.get("diagnostic_notes") or []

    return (
        "SOURCE\n"
        f"- Source ID: {source['source_id']}\n"
        f"- Input Type: {source['input_type']}\n"
        f"- Transcript Status: {source['transcript_status']}\n"
        f"- Source Type: {source['source_type']}\n"
        f"- Speaker Type: {source['speaker_type']}\n"
        f"- URL: {source['url'] or 'None'}\n"
        f"- Video ID: {source['video_id'] or 'None'}\n\n"
        "PROVENANCE\n"
        f"- Origin Cluster ID: {provenance['origin_cluster_id'] or 'None'}\n"
        f"- Origin Register: {provenance['origin_register'] or 'None'}\n"
        f"- Query Used: {provenance['query_used'] or 'None'}\n\n"
        "PASS 1: WILLINGNESS-TO-PAY SIGNALS\n\n"
        "BEHAVIOR-LEVEL SIGNALS (High WTP Evidence)\n"
        f"{render_signal_blocks(pass1['behavior_signals'], ['QUOTE', 'CATEGORY', 'WTP IMPLICATION'])}\n\n"
        "OPINION-LEVEL SIGNALS (Low WTP Evidence)\n"
        f"{render_signal_blocks(pass1['opinion_signals'], ['QUOTE', 'WHY LOW SIGNAL'])}\n\n"
        "PASS 1 SUMMARY\n"
        f"- Total high-signal moments: {pass1['summary']['total_high_signal_moments']}\n"
        f"- Dominant pain category: {pass1['summary']['dominant_pain_category']}\n"
        f"- Confidence level: {pass1['summary']['confidence_level']}\n\n"
        "PASS 2: FGP PIPELINE INTELLIGENCE\n\n"
        "CATEGORY A — CASCADE INDICATORS\n"
        f"{render_signal_blocks(pass2['cascade_indicators'], ['QUOTE', 'LAYERS BROKEN', 'CASCADE DEPTH', 'BUILD SIGNAL'])}\n\n"
        "CATEGORY B — GATEKEEPER MENTIONS\n"
        f"{render_signal_blocks(pass2['gatekeeper_mentions'], ['QUOTE', 'ENTITY NAMED', 'DEPENDENCY TYPE', 'OPERATOR RELATIONSHIP', 'GATEKEEPER SIGNAL'])}\n\n"
        "CATEGORY C — POSITION INTELLIGENCE\n"
        f"{render_signal_blocks(pass2['position_intelligence'], ['QUOTE', 'ENTITY', 'WHAT THEY PROTECT', 'CONFIDENCE'])}\n\n"
        "CATEGORY D — SUBNICHE CULTURE SIGNALS\n"
        f"{render_signal_blocks(pass2['subniche_culture_signals'], ['QUOTE', 'SUBNICHE IDENTIFIED', 'DIFFERENTIATION CLAIM', 'FGP USE'])}\n\n"
        "PASS 2 SUMMARY\n"
        f"- Strongest cascade found: {pass2['summary']['strongest_cascade_found']}\n"
        f"- Highest-signal gatekeeper mention: {pass2['summary']['highest_signal_gatekeeper_mention']}\n"
        f"- Position intelligence confidence: {pass2['summary']['position_intelligence_confidence']}\n"
        f"- Recommended next action: {pass2['summary']['recommended_next_action']}\n\n"
        "COMBINED INTELLIGENCE SUMMARY\n\n"
        "TOP 3 ACTIONABLE SIGNALS ACROSS BOTH PASSES:\n"
        f"{render_top_signals(combined['top_3_actionable_signals'])}\n\n"
        "ONE HYPOTHESIS WORTH TESTING:\n"
        f"{combined['hypothesis_worth_testing']}\n\n"
        "DIAGNOSTICS\n"
        f"- Phase Fit: {diagnostics['phase_fit']}\n"
        f"- Signal Density: {diagnostics['signal_density']}\n"
        f"- Recommended Next Phase: {diagnostics['recommended_next_phase']}\n\n"
        "NAMED ENTITIES\n"
        f"{render_named_entities(diagnostics['named_entities'])}\n\n"
        "GATEKEEPERS\n"
        f"{render_gatekeepers(diagnostics['gatekeepers'])}\n\n"
        "REGISTER ALIGNMENT\n"
        f"{render_register_alignment(diagnostics['register_alignment'])}\n\n"
        "SEARCH LANGUAGE FEEDBACK\n"
        f"- Likely Too Generic: {search_feedback['likely_too_generic']}\n"
        f"- Too Vendor Heavy: {search_feedback['too_vendor_heavy']}\n"
        f"- Off Phase: {search_feedback['off_phase']}\n"
        f"- Likely Operator Facing: {search_feedback['likely_operator_facing']}\n"
        f"- Likely Gatekeeper Facing: {search_feedback['likely_gatekeeper_facing']}\n"
        f"- Reason: {search_feedback['reason']}\n\n"
        "DIAGNOSTIC NOTES\n"
        + ("\n".join(f"- {note}" for note in diagnostic_notes) if diagnostic_notes else "None found.")
        + "\n\nPARSE WARNINGS\n"
        + f"{render_parse_warnings(result['parse_warnings'])}"
    )


def render_session_report(session_result: dict[str, Any]) -> str:
    aggregate_notes = session_result.get("aggregate_notes") or []
    manifest_path = session_result.get("manifest_path") or "None"

    return (
        "SESSION SUMMARY\n"
        f"- Session ID: {session_result['session_id']}\n"
        f"- Source Count: {session_result['source_count']}\n"
        f"- Recommended Next Phase: {session_result['recommended_next_phase']}\n"
        f"- Manifest Path: {manifest_path}\n\n"
        "SESSION CONTEXT\n"
        f"{render_session_context(session_result.get('session_context') or {})}\n\n"
        "SOURCES\n"
        f"{render_session_sources(session_result.get('sources') or [])}\n\n"
        "REGISTER PERFORMANCE\n"
        f"{render_register_alignment(session_result['register_performance'])}\n\n"
        "GATEKEEPER TYPE DISTRIBUTION\n"
        f"{render_count_blocks(session_result['gatekeeper_type_distribution'], 'gatekeeper_type', 'count')}\n\n"
        "RECURRING ENTITIES\n"
        f"{render_recurring_entities(session_result['recurring_entities'])}\n\n"
        "SOURCE TYPE PERFORMANCE\n"
        f"{render_count_blocks(session_result['source_type_performance'], 'source_type', 'signal_total')}\n\n"
        "QUERY FEEDBACK\n"
        f"{render_query_feedback(session_result['query_feedback'])}\n\n"
        "AGGREGATE NOTES\n"
        + ("\n".join(f"- {note}" for note in aggregate_notes) if aggregate_notes else "None found.")
    )
