"""The machine contract: versions, exit codes, statuses, and a self-description.

An agent driving this CLI should never have to read source code to use it.
`python main.py --describe` prints describe() as JSON: every flag, exit code,
status, vocabulary, output shape and domain term in one document.
"""
from __future__ import annotations

from typing import Any

from wtp.install import current_version
from wtp.schemas import (
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
    empty_result,
)

TOOL_VERSION = current_version()  # from the installed package metadata (pyproject.toml)
# Bump on any breaking change to the result or session JSON shape.
SCHEMA_VERSION = "2"

# Exit codes. For multi-source runs the process exits with the worst code seen.
EXIT_OK = 0              # every source analyzed, no parse warnings
EXIT_DEGRADED = 1        # analyzed, but parse warnings or unverifiable quotes
EXIT_USAGE = 2           # bad flags, missing config, unreadable manifest/file
EXIT_SOURCE_FAILED = 3   # a transcript could not be fetched or was empty
EXIT_ANALYSIS_FAILED = 4  # the model call failed

EXIT_CODES = {
    EXIT_OK: "ok: every source analyzed cleanly",
    EXIT_DEGRADED: "degraded: analyzed, but with parse warnings or quotes not found in the transcript",
    EXIT_USAGE: "usage: bad flags, missing API key/config, or unreadable input file",
    EXIT_SOURCE_FAILED: "source_failed: transcript fetch failed or transcript empty",
    EXIT_ANALYSIS_FAILED: "analysis_failed: the model/provider call raised an error",
}

STATUS_EXIT = {
    "ok": EXIT_OK,
    "degraded": EXIT_DEGRADED,
    "transcript_failed": EXIT_SOURCE_FAILED,
    "analysis_failed": EXIT_ANALYSIS_FAILED,
}

SEVERITY = [EXIT_OK, EXIT_DEGRADED, EXIT_SOURCE_FAILED, EXIT_ANALYSIS_FAILED, EXIT_USAGE]


def worst_exit(codes: list[int]) -> int:
    if not codes:
        return EXIT_OK
    return max(codes, key=SEVERITY.index)


# Domain knowledge the model gets in prompt.py, restated for the agent that
# reads the results. Without it, "phase 3.5" or "Type2" means nothing.
DOMAIN = {
    "wtp": "Willingness to pay. Behavior-level signals (money already spent, tools bought then "
           "abandoned, workarounds in use, urgency/consequence language) are strong evidence. "
           "Opinion-level signals (wishes, hypotheticals, complaints without action) are weak.",
    "fgp_phases": {
        "0": "Frame: sub-niche identity and differentiation (pass2.subniche_culture_signals).",
        "1": "Pain/WTP validation (pass1 signals).",
        "2": "Cascade: friction that breaks layers downstream of the operator (pass2.cascade_indicators).",
        "3": "Gatekeepers: intermediaries the operator depends on or cannot bypass (pass2.gatekeeper_mentions).",
        "3.5": "Position: what a gatekeeper protects or optimizes for (pass2.position_intelligence).",
        "mixed": "Signals for several phases.",
        "unknown": "Not enough evidence.",
    },
    "gatekeeper_types": {
        "Type1": "Owns a process others cannot bypass (structural_friction).",
        "Type2": "Their word moves the network (social_authority).",
        "Type3": "Controls information others need (information_asymmetry).",
        "Type4": "Platform controlling access to customers (platform).",
    },
    "registers": "Source Garden search-language families. A register's matched_signals counts how many "
                 "extracted signals look like that kind of language; use it to judge which search "
                 "language found this source.",
    "source_garden": "Sibling system (source-garden-intelligence) that decides where to look. This tool "
                     "judges what was found. provenance.* and diagnostics.search_language_feedback "
                     "are the feedback path to it.",
}

FIELD_GUIDE = {
    "status": "ok | degraded | transcript_failed | analysis_failed. Check this first.",
    "source": "Where the text came from. transcript_path points at the saved transcript text.",
    "provenance": "Optional upstream metadata (from a session manifest): which cluster/register/query found this source.",
    "pass1": "WTP signals. behavior_signals = strong, opinion_signals = weak. Keys are UPPERCASE labels from the model.",
    "pass2": "FGP signals: cascade_indicators, gatekeeper_mentions, position_intelligence, subniche_culture_signals.",
    "diagnostics": "Normalized judgments about the source. diagnostics.field_sources says, per field, "
                   "whether the value came from the model ('llm'), a local heuristic ('heuristic'), "
                   "or nothing ('default'). Trust 'llm' and 'heuristic' differently.",
    "evidence": "Every quote checked against the transcript. verified: exact after normalizing case "
                "and punctuation. approximate: >= 80% of the quote's words appear in order in one "
                "stretch (small edits, elided filler). stitched: each sentence/fragment is real but "
                "they come from different places or a different order; cite the fragments separately. "
                "not_found: probably paraphrased or invented; do not cite as the speaker's words. "
                "Any not_found sets status=degraded.",
    "combined_summary": "Model's top 3 actionable signals and one falsifiable hypothesis.",
    "parse_warnings": "Sections the parser expected but did not find. Non-empty means status=degraded.",
    "raw_output": "The model's full text answer. Re-parse it offline with --replay.",
    "run": "Provenance of this run: tool/schema version, mode (live|replay), output_format "
           "(json | legacy_text = pre-0.3 runs), structured_mode (json_schema = server enforced "
           "the schema | json_object = only JSON enforced, schema checked locally), attempts per step "
           "({transcript, model}), provider, model, prompt hash (prompt + schema), timing.",
    "error": "Present only when status is *_failed: the exception, with the attempt count.",
    "next_step": "Present only when status is *_failed: what to do next, in wtp's terms "
                 "(wait, --transcript-file, WTP_YT_PROXY, fix the key, switch model or provider).",
    "artifacts": "Paths of every file this run wrote.",
}


def manifest_example() -> dict[str, Any]:
    return {
        "session_id": "dental-premium-2026-10",
        "session_context": {
            "vertical": "dental",
            "operator_type": "clinic_owner",
            "targeted_subniche": "premium_clinic",
            "fgp_phase": "3",
            "gatekeeper_type": None,
            "currency_window": None,
            "session_date": None,
            "prior_loop_map_phase": None,
        },
        "sources": [
            {"source_id": "s1", "url": "https://youtu.be/VIDEO_ID",
             "provenance": {"origin_cluster_id": "c1", "origin_register": "complaint_register",
                            "query_used": "premium clinic booking dependency"}},
            {"source_id": "s2", "transcript": "Full transcript text pasted inline..."},
        ],
    }


def describe(cli_flags: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tool": "wtp-signal-extractor",
        "tool_version": TOOL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "purpose": "Extract willingness-to-pay (WTP) and FGP pipeline signals from interview/video "
                   "transcripts with an LLM, then verify and diagnose them.",
        "install": "uv tool install git+https://github.com/breexzed/WTP-Signal-Extractor@<tag>; "
                   "update with `wtp --self-update` (or `wtp --check-update` to only look)",
        "agent_quickstart": [
            "wtp --check            # preflight: config, keys present, paths; no network",
            "wtp --url URL --json   # one YouTube source -> result JSON on stdout",
            "wtp --transcript-file f.txt --json   # or '-' for stdin",
            "wtp --session manifest.json --json   # many sources -> session JSON on stdout",
            "wtp --replay raw.txt --transcript-file f.txt --json   # re-parse, no API call",
        ],
        "io_rules": [
            "With --json, stdout carries exactly one JSON document; everything else goes to stderr.",
            "Without --json, stdout carries the human report.",
            "Artifacts are always written; their paths are in result.artifacts.",
            "Never interactive unless stdin is a TTY and no input flag is given.",
        ],
        "flags": cli_flags,
        "exit_codes": {str(k): v for k, v in EXIT_CODES.items()},
        "environment": {
            "LLM_PROVIDER": "gemini (default) | anthropic (Claude; default claude-opus-5-5) | ollama | "
                            "llamacpp | groq | openrouter | openai | "
                            "openai_compatible (any Chat Completions server; set LLM_BASE_URL)",
            "LLM_MODEL_NAME": "model for any provider (required except gemini: default gemini-3.8-flash)",
            "keys": "GEMINI_API_KEY | ANTHROPIC_API_KEY (or an `ant auth login` profile) | GROQ_API_KEY | OPENROUTER_API_KEY | OPENAI_API_KEY | "
                    "OPENAI_COMPATIBLE_API_KEY, or LLM_API_KEY for any; ollama/llamacpp need none",
            "LLM_BASE_URL": "override the provider's base URL (required for openai_compatible)",
            "WTP_MAX_ATTEMPTS": "tries per model call / transcript fetch, default 3",
            "WTP_RETRY_BASE_DELAY": "seconds before the 1st retry, doubled each time (+<=25% jitter), default 2",
            ".env": "read from the working directory, then ~/.config/wtp/.env (WTP_CONFIG_DIR); "
                    "real environment variables win",
            "WTP_YT_PROXY": "http(s) proxy URL for YouTube caption fetches (works around IP blocks)",
            "WTP_DATA_DIR": "where runs are saved, default ~/.local/share/wtp (runs/, sessions/<id>/)",
            "free_options": "ollama/llamacpp (local, no key, no quota); gemini, groq, openrouter ':free' "
                            "models have rate-limited free tiers. `--check` shows what is configured.",
        },
        "vocabularies": {
            "phase": sorted(PHASE_VALUES),
            "signal_density": sorted(SIGNAL_DENSITY_VALUES),
            "source_type": sorted(SOURCE_TYPE_VALUES),
            "speaker_type": sorted(SPEAKER_TYPE_VALUES),
            "entity_kind": sorted(ENTITY_KIND_VALUES),
            "entity_relationship": sorted(ENTITY_RELATIONSHIP_VALUES),
            "gatekeeper_relationship": sorted(GATEKEEPER_RELATIONSHIP_VALUES),
            "dependency_type": sorted(DEPENDENCY_TYPE_VALUES),
            "gatekeeper_type": sorted(GATEKEEPER_TYPE_VALUES),
            "confidence": sorted(CONFIDENCE_VALUES),
            "register": REGISTER_NAMES,
            "status": list(STATUS_EXIT),
            "quote_status": ["verified", "approximate", "stitched", "not_found"],
            "field_source": ["llm", "heuristic", "default"],
        },
        "domain": DOMAIN,
        "result_fields": FIELD_GUIDE,
        "retries": "Transient errors (429, 5xx, timeouts, dropped connections, a reply that is not "
                   "valid JSON) are retried with exponential backoff. Permanent ones (401/403/404, "
                   "no captions, video unavailable, YouTube IP block) fail on the first try. "
                   "A 429 that persists across retries usually means quota, not load.",
        "model_output_schema": "model_output.MODEL_OUTPUT_SCHEMA (JSON Schema the provider enforces).",
        "result_skeleton": empty_result(),
        "manifest_example": manifest_example(),
    }
