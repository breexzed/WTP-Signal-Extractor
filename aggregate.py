from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from diagnostics import aggregate_named_entities, most_common_phase


def aggregate_source_results(
    results: list[dict[str, Any]],
    session_id: str = "single-source-session",
) -> dict[str, Any]:
    register_counts: defaultdict[str, dict[str, Any]] = defaultdict(
        lambda: {"register": "", "matched_signals": 0, "source_hits": 0}
    )
    gatekeeper_counter: Counter[str] = Counter()
    source_type_counter: Counter[str] = Counter()
    source_type_signal_totals: defaultdict[str, int] = defaultdict(int)
    query_feedback = []

    for result in results:
        source_id = result["source"]["source_id"]
        source_type = result["source"]["source_type"]
        source_type_counter[source_type] += 1
        signal_total = result["pass1"]["summary"]["total_high_signal_moments"] + len(
            result["pass2"]["gatekeeper_mentions"]
        ) + len(result["pass2"]["cascade_indicators"])
        source_type_signal_totals[source_type] += signal_total

        for item in result["diagnostics"]["register_alignment"]:
            register = item["register"]
            bucket = register_counts[register]
            bucket["register"] = register
            bucket["matched_signals"] += int(item["matched_signals"])
            bucket["source_hits"] += 1

        for gatekeeper in result["diagnostics"]["gatekeepers"]:
            gatekeeper_counter[gatekeeper["gatekeeper_type"]] += 1

        feedback = dict(result["diagnostics"]["search_language_feedback"])
        feedback["source_id"] = source_id
        feedback["query_used"] = result["provenance"]["query_used"]
        query_feedback.append(feedback)

    register_performance = sorted(
        register_counts.values(),
        key=lambda item: (-item["matched_signals"], item["register"]),
    )
    gatekeeper_type_distribution = [
        {"gatekeeper_type": gatekeeper_type, "count": count}
        for gatekeeper_type, count in gatekeeper_counter.most_common()
    ]
    recurring_entities = aggregate_named_entities(results)
    source_type_performance = [
        {
            "source_type": source_type,
            "source_count": count,
            "signal_total": source_type_signal_totals[source_type],
        }
        for source_type, count in source_type_counter.most_common()
    ]

    aggregate_notes = []
    if any(item["likely_too_generic"] for item in query_feedback):
        aggregate_notes.append("At least one source suggests the upstream search language was too generic.")
    if any(item["too_vendor_heavy"] for item in query_feedback):
        aggregate_notes.append("At least one source appears too vendor-heavy for clean operator diagnostics.")
    if not aggregate_notes:
        aggregate_notes.append("No major aggregate diagnostic issues were detected across the current source set.")

    return {
        "session_id": session_id,
        "source_count": len(results),
        "register_performance": register_performance,
        "gatekeeper_type_distribution": gatekeeper_type_distribution,
        "recurring_entities": recurring_entities,
        "source_type_performance": source_type_performance,
        "query_feedback": query_feedback,
        "recommended_next_phase": most_common_phase(results),
        "aggregate_notes": aggregate_notes,
    }
