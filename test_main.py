from __future__ import annotations

import io
import json
import shutil
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main
from aggregate import aggregate_source_results
from diagnostics import build_diagnostics
from extract import parse_model_output
from render import render_result, safe_console_text
from schemas import REGISTER_NAMES, merge_result
from session_store import write_artifacts


SAMPLE_RAW_OUTPUT = """
PASS 1: WILLINGNESS-TO-PAY SIGNALS

BEHAVIOR-LEVEL SIGNALS (High WTP Evidence)
- QUOTE: "We paid for two scheduling tools"
- CATEGORY: Money Spent
- WTP IMPLICATION: They already spend to solve this problem.

- QUOTE: "then abandoned them"
- CATEGORY: Tool Abandoned
- WTP IMPLICATION: Existing tools failed to fit the workflow.

OPINION-LEVEL SIGNALS (Low WTP Evidence)
- QUOTE: "It would be nice if intake was cleaner"
- WHY LOW SIGNAL: This is a preference statement without action.

PASS 1 SUMMARY
- Total high-signal moments: 2
- Dominant pain category: Money Spent
- Confidence level: High

PASS 2: FGP PIPELINE INTELLIGENCE

CATEGORY A - CASCADE INDICATORS
- QUOTE: "missing appointments was costing us clients"
- LAYERS BROKEN: operator -> clients
- CASCADE DEPTH: Two-layer
- BUILD SIGNAL: Worth building for because clients are directly affected.

CATEGORY B - GATEKEEPER MENTIONS
- QUOTE: "We still depend on Zocdoc because they control intake volume"
- ENTITY NAMED: Zocdoc
- DEPENDENCY TYPE: platform
- OPERATOR RELATIONSHIP: dependent
- GATEKEEPER SIGNAL: This platform controls a key customer-acquisition path.

CATEGORY C - POSITION INTELLIGENCE
- QUOTE: "they mostly care about keeping throughput high"
- ENTITY: Zocdoc
- WHAT THEY PROTECT: They optimize for throughput and high booking flow.
- CONFIDENCE: Medium

CATEGORY D - SUBNICHE CULTURE SIGNALS
- QUOTE: "We're not trying to be the cheapest clinic in town"
- SUBNICHE IDENTIFIED: Premium dental clinic
- DIFFERENTIATION CLAIM: The operator competes on quality rather than price.
- FGP USE: Both

PASS 2 SUMMARY
- Strongest cascade found: "missing appointments was costing us clients" (Two-layer)
- Highest-signal gatekeeper mention: Zocdoc (platform)
- Position intelligence confidence: Medium
- Recommended next action: Phase 3 - investigate the booking platform and its incentives.

COMBINED INTELLIGENCE SUMMARY

TOP 3 ACTIONABLE SIGNALS ACROSS BOTH PASSES:
1. The operator already spends and churns tools - Pass 1 - strong buying behavior.
2. Client harm cascades downstream - Pass 2 - build priority is clear.
3. Zocdoc appears as a recurring gatekeeper - Pass 2 - dependency should be investigated.

ONE HYPOTHESIS WORTH TESTING:
If premium clinics could reduce missed appointments without depending on booking platforms, they would switch spend toward a dedicated workflow solution.

SOURCE DIAGNOSTICS
- SOURCE TYPE: operator_interview
- SPEAKER TYPE: operator
- PHASE FIT: 3
- SIGNAL DENSITY: high

NAMED ENTITIES
- NAME: Zocdoc
- ENTITY KIND: platform
- RELATIONSHIP: dependent
- SUPPORTING QUOTE: "We still depend on Zocdoc because they control intake volume"
- CONFIDENCE: high

GATEKEEPER OBJECTS
- ENTITY: Zocdoc
- DEPENDENCY TYPE: platform
- GATEKEEPER TYPE: Type4
- OPERATOR RELATIONSHIP: dependent
- SUPPORTING QUOTE: "We still depend on Zocdoc because they control intake volume"
- CONFIDENCE: high

REGISTER ALIGNMENT
- REGISTER: complaint_register
- MATCHED SIGNALS: 2
- STRENGTH: medium

- REGISTER: intermediary_register
- MATCHED SIGNALS: 1
- STRENGTH: low

SEARCH LANGUAGE FEEDBACK
- LIKELY TOO GENERIC: false
- TOO VENDOR HEAVY: false
- OFF PHASE: false
- LIKELY OPERATOR FACING: true
- LIKELY GATEKEEPER FACING: false
- REASON: The source is strongly operator-facing and contains named dependency evidence.

DIAGNOSTIC NOTES
1. Strong operator pain with one named platform dependency.
"""


def build_result_from_raw(
    raw_output: str,
    transcript_text: str,
    source_id: str = "test-source",
    input_type: str = "pasted_transcript",
    transcript_status: str = "pasted",
    url: str | None = None,
    video_id: str | None = None,
    provenance: dict[str, str | None] | None = None,
) -> dict[str, object]:
    parsed = parse_model_output(raw_output)
    provenance = provenance or {
        "origin_cluster_id": None,
        "origin_register": "complaint_register",
        "query_used": "dental clinic scheduling pain points 2026",
    }
    diagnostics = build_diagnostics(parsed, transcript_text, provenance)
    source = {
        "source_id": source_id,
        "url": url,
        "video_id": video_id,
        "input_type": input_type,
        "transcript_status": transcript_status,
        "source_type": diagnostics.pop("source_type"),
        "speaker_type": diagnostics.pop("speaker_type"),
    }
    return merge_result(
        source=source,
        provenance=provenance,
        pass1=parsed["pass1"],
        pass2=parsed["pass2"],
        diagnostics=diagnostics,
        combined_summary=parsed["combined_summary"],
        parse_warnings=parsed["parse_warnings"],
        raw_output=parsed["raw_output"],
    )


class MainTests(unittest.TestCase):
    def test_parse_model_output_returns_structured_sections(self):
        parsed = parse_model_output(SAMPLE_RAW_OUTPUT)

        self.assertEqual(len(parsed["pass1"]["behavior_signals"]), 2)
        self.assertEqual(parsed["pass1"]["summary"]["total_high_signal_moments"], 2)
        self.assertEqual(len(parsed["pass2"]["gatekeeper_mentions"]), 1)
        self.assertEqual(parsed["combined_summary"]["top_3_actionable_signals"][0], "The operator already spends and churns tools - Pass 1 - strong buying behavior.")
        self.assertEqual(parsed["diagnostic_hints"]["source_type"], "operator_interview")

    def test_parse_model_output_preserves_warnings_when_sections_are_missing(self):
        parsed = parse_model_output("PASS 1 SUMMARY\n- Confidence level: Low")

        self.assertTrue(parsed["parse_warnings"])
        self.assertEqual(parsed["pass1"]["summary"]["confidence_level"], "Low")
        self.assertEqual(parsed["combined_summary"]["hypothesis_worth_testing"], "None found.")

    def test_build_diagnostics_derives_named_entities_and_gatekeepers(self):
        result = build_result_from_raw(
            SAMPLE_RAW_OUTPUT,
            transcript_text=(
                "We paid for tools, lost clients from missed appointments, and still depend on Zocdoc."
            ),
        )

        named_entity = result["diagnostics"]["named_entities"][0]
        gatekeeper = result["diagnostics"]["gatekeepers"][0]

        self.assertEqual(named_entity["name"], "Zocdoc")
        self.assertEqual(named_entity["entity_kind"], "platform")
        self.assertEqual(gatekeeper["entity"], "Zocdoc")
        self.assertEqual(gatekeeper["gatekeeper_type"], "Type4")
        self.assertEqual(gatekeeper["dependency_type"], "platform")

    def test_register_alignment_only_uses_source_garden_registers(self):
        result = build_result_from_raw(
            SAMPLE_RAW_OUTPUT,
            transcript_text="2026 operator discussion about Zocdoc and client loss.",
        )

        for item in result["diagnostics"]["register_alignment"]:
            self.assertIn(item["register"], REGISTER_NAMES)

    def test_render_result_includes_structured_diagnostics_sections(self):
        result = build_result_from_raw(
            SAMPLE_RAW_OUTPUT,
            transcript_text="We paid for tools and depend on Zocdoc.",
        )
        rendered = render_result(result)

        self.assertIn("SOURCE", rendered)
        self.assertIn("NAMED ENTITIES", rendered)
        self.assertIn("GATEKEEPERS", rendered)
        self.assertIn("REGISTER ALIGNMENT", rendered)
        self.assertIn("PARSE WARNINGS", rendered)

    def test_safe_console_text_normalizes_common_unicode(self):
        text = 'operator -> client \u2014 "quoted" \u2192 next'
        normalized = safe_console_text(text)
        self.assertEqual(normalized, 'operator -> client - "quoted" -> next')

    def test_write_artifacts_creates_json_and_text_files(self):
        result = build_result_from_raw(
            SAMPLE_RAW_OUTPUT,
            transcript_text="We paid for tools and depend on Zocdoc.",
        )
        text_report = render_result(result)

        temp_dir = Path("test-output-write")
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            paths = write_artifacts(
                result,
                text_report,
                output_dir=temp_dir,
                session_id="session-1",
                timestamp=datetime(2026, 5, 7, 12, 0, 0),
            )

            self.assertTrue(Path(paths["text_path"]).exists())
            self.assertTrue(Path(paths["json_path"]).exists())

            payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["source"]["source_id"], "test-source")
            self.assertEqual(payload["diagnostics"]["gatekeepers"][0]["entity"], "Zocdoc")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_aggregate_source_results_rolls_up_session_diagnostics(self):
        result_one = build_result_from_raw(
            SAMPLE_RAW_OUTPUT,
            transcript_text="We paid for tools and depend on Zocdoc.",
            source_id="source-1",
        )
        result_two = build_result_from_raw(
            SAMPLE_RAW_OUTPUT.replace("Zocdoc", "Doctolib"),
            transcript_text="We paid for tools and depend on Doctolib.",
            source_id="source-2",
            provenance={
                "origin_cluster_id": "cluster-2",
                "origin_register": "intermediary_register",
                "query_used": "clinic booking platform dependency 2026",
            },
        )

        aggregate = aggregate_source_results([result_one, result_two], session_id="session-aggregate")

        self.assertEqual(aggregate["session_id"], "session-aggregate")
        self.assertEqual(aggregate["source_count"], 2)
        self.assertTrue(aggregate["register_performance"])
        self.assertTrue(aggregate["gatekeeper_type_distribution"])
        self.assertTrue(aggregate["recurring_entities"])
        self.assertEqual(aggregate["recommended_next_phase"], "3")

    @patch("main.YouTubeTranscriptApi")
    def test_get_transcript_from_url_returns_joined_text(self, transcript_api_cls):
        transcript_api_cls.return_value.fetch.return_value = [
            {"text": "paid for three tools"},
            SimpleNamespace(text="and built a workaround"),
        ]

        transcript = main.get_transcript_from_url(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )

        self.assertEqual(transcript, "paid for three tools and built a workaround")

    def test_extract_video_id_from_short_url(self):
        video_id = main.extract_video_id("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(video_id, "dQw4w9WgXcQ")

    def test_end_to_end_mocked_cli_flow_writes_text_and_json(self):
        temp_dir = Path("test-output-cli")
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            real_write_artifacts = write_artifacts

            def write_to_temp(result, text_report):
                return real_write_artifacts(
                    result,
                    text_report,
                    output_dir=temp_dir,
                    session_id="cli-session",
                    timestamp=datetime(2026, 5, 7, 12, 0, 1),
                )

            stdout = io.StringIO()
            with patch("builtins.input", side_effect=["2", "We paid for two tools and still depend on Zocdoc.", "End"]), patch(
                "main.call_model",
                return_value=SAMPLE_RAW_OUTPUT,
            ), patch(
                "main.write_artifacts",
                side_effect=write_to_temp,
            ), redirect_stdout(stdout):
                main.main()

            files = list(Path(temp_dir).iterdir())
            self.assertEqual(len(files), 2)
            output = stdout.getvalue()
            self.assertIn("=== RESULTS ===", output)
            self.assertIn("Artifacts saved:", output)
            self.assertTrue(any(file.suffix == ".json" for file in files))
            self.assertTrue(any(file.suffix == ".txt" for file in files))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
