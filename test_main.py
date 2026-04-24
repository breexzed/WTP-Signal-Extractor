import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import main


class MainTests(unittest.TestCase):
    def test_safe_console_text_normalizes_common_unicode(self):
        text = 'operator -> client \u2014 "quoted" \u2192 next'
        normalized = main.safe_console_text(text)
        self.assertEqual(normalized, 'operator -> client - "quoted" -> next')

    def test_format_analysis_output_normalizes_multi_pass_response(self):
        raw_output = """
        PASS 1: WILLINGNESS-TO-PAY SIGNALS
        BEHAVIOR LEVEL SIGNALS (High WTP Evidence)
        - QUOTE: "We paid for two scheduling tools"
          - CATEGORY: Money Spent
          - WTP IMPLICATION: They already spend to solve this.
        - QUOTE: "then abandoned them"
          - CATEGORY: Tool Abandoned
          - WTP IMPLICATION: Current tools failed.

        OPINION LEVEL SIGNALS (Low WTP Evidence)
        None found.

        PASS 1 SUMMARY
        - Total high-signal moments: 2
        - Dominant pain category: Money Spent
        - Confidence level: High

        CATEGORY A - CASCADE INDICATORS
        - QUOTE: "Missing appointments was costing us clients"
          - LAYERS BROKEN: operator -> client
          - CASCADE DEPTH: Two-layer
          - BUILD SIGNAL: Worth building for because the loss reaches the client layer.

        CATEGORY B - GATEKEEPER MENTIONS
        - QUOTE: "We depended on the booking platform"
          - ENTITY NAMED: Booking platform
          - DEPENDENCY TYPE: Platform
          - OPERATOR RELATIONSHIP: Dependent
          - GATEKEEPER SIGNAL: This platform has structural control over bookings.

        CATEGORY C - POSITION INTELLIGENCE
        - QUOTE: "They only care about keeping volume high"
          - ENTITY: Booking platform
          - WHAT THEY PROTECT: They appear to protect throughput over operator flexibility.
          - CONFIDENCE: Medium

        CATEGORY D - SUBNICHE CULTURE SIGNALS
        - QUOTE: "We're not trying to be the cheapest clinic in town"
          - SUBNICHE IDENTIFIED: Premium dental clinic
          - DIFFERENTIATION CLAIM: The operator is positioning around quality over price.
          - FGP USE: Both

        PASS 2 SUMMARY
        - Strongest cascade found: "Missing appointments was costing us clients" (Two-layer)
        - Highest-signal gatekeeper mention: Booking platform (Platform)
        - Position intelligence confidence: Medium
        - Recommended next action: Feed this into Phase 3 gatekeeper research first.

        COMBINED INTELLIGENCE SUMMARY
        TOP 3 ACTIONABLE SIGNALS ACROSS BOTH PASSES:
        1. The operator already pays and churns tools - Pass 1 - strong buyer intent.
        2. Client harm cascades downstream - Pass 2 - sharper build priority.
        3. The booking platform has dependency power - Pass 2 - investigate control points.

        ONE HYPOTHESIS WORTH TESTING:
        If premium clinics could prevent missed bookings without relying on a platform, they would switch spend toward a dedicated workflow tool.
        """

        formatted = main.format_analysis_output(raw_output)

        expected = """PASS 1: WILLINGNESS-TO-PAY SIGNALS

BEHAVIOR-LEVEL SIGNALS (High WTP Evidence)
- QUOTE: "We paid for two scheduling tools"
- CATEGORY: Money Spent
- WTP IMPLICATION: They already spend to solve this.

- QUOTE: "then abandoned them"
- CATEGORY: Tool Abandoned
- WTP IMPLICATION: Current tools failed.

OPINION-LEVEL SIGNALS (Low WTP Evidence)
None found.

PASS 1 SUMMARY
- Total high-signal moments: 2
- Dominant pain category: Money Spent
- Confidence level: High

PASS 2: FGP PIPELINE INTELLIGENCE

CATEGORY A — CASCADE INDICATORS
- QUOTE: "Missing appointments was costing us clients"
- LAYERS BROKEN: operator -> client
- CASCADE DEPTH: Two-layer
- BUILD SIGNAL: Worth building for because the loss reaches the client layer.

CATEGORY B — GATEKEEPER MENTIONS
- QUOTE: "We depended on the booking platform"
- ENTITY NAMED: Booking platform
- DEPENDENCY TYPE: Platform
- OPERATOR RELATIONSHIP: Dependent
- GATEKEEPER SIGNAL: This platform has structural control over bookings.

CATEGORY C — POSITION INTELLIGENCE
- QUOTE: "They only care about keeping volume high"
- ENTITY: Booking platform
- WHAT THEY PROTECT: They appear to protect throughput over operator flexibility.
- CONFIDENCE: Medium

CATEGORY D — SUBNICHE CULTURE SIGNALS
- QUOTE: "We're not trying to be the cheapest clinic in town"
- SUBNICHE IDENTIFIED: Premium dental clinic
- DIFFERENTIATION CLAIM: The operator is positioning around quality over price.
- FGP USE: Both

PASS 2 SUMMARY
- Strongest cascade found: "Missing appointments was costing us clients" (Two-layer)
- Highest-signal gatekeeper mention: Booking platform (Platform)
- Position intelligence confidence: Medium
- Recommended next action: Feed this into Phase 3 gatekeeper research first.

COMBINED INTELLIGENCE SUMMARY

TOP 3 ACTIONABLE SIGNALS ACROSS BOTH PASSES:
1. The operator already pays and churns tools - Pass 1 - strong buyer intent.
2. Client harm cascades downstream - Pass 2 - sharper build priority.
3. The booking platform has dependency power - Pass 2 - investigate control points.

ONE HYPOTHESIS WORTH TESTING:
If premium clinics could prevent missed bookings without relying on a platform, they would switch spend toward a dedicated workflow tool."""
        self.assertEqual(formatted, expected)

    def test_format_analysis_output_falls_back_cleanly_when_missing_sections(self):
        formatted = main.format_analysis_output("No clear signals found.")

        expected = """PASS 1: WILLINGNESS-TO-PAY SIGNALS

BEHAVIOR-LEVEL SIGNALS (High WTP Evidence)
None found.

OPINION-LEVEL SIGNALS (Low WTP Evidence)
None found.

PASS 1 SUMMARY
- Total high-signal moments: 0
- Dominant pain category: None found.
- Confidence level: Not provided.

PASS 2: FGP PIPELINE INTELLIGENCE

CATEGORY A — CASCADE INDICATORS
None found.

CATEGORY B — GATEKEEPER MENTIONS
None found.

CATEGORY C — POSITION INTELLIGENCE
None found.

CATEGORY D — SUBNICHE CULTURE SIGNALS
None found.

PASS 2 SUMMARY
- Strongest cascade found: None found.
- Highest-signal gatekeeper mention: None found.
- Position intelligence confidence: Low
- Recommended next action: Not provided.

COMBINED INTELLIGENCE SUMMARY

TOP 3 ACTIONABLE SIGNALS ACROSS BOTH PASSES:
1. None found.
2. None found.
3. None found.

ONE HYPOTHESIS WORTH TESTING:
None found."""
        self.assertEqual(formatted, expected)

    def test_normalize_youtube_input_extracts_first_url_from_pasted_text(self):
        raw_text = (
            'Videos: "How I Would 2X a Firm" '
            "(https://www.youtube.com/watch?v=Kdr3fxgRLVU or "
            "https://www.youtube.com/watch?v=KIcCix_lQjQ)"
        )
        normalized = main.normalize_youtube_input(raw_text)
        self.assertEqual(normalized, "https://www.youtube.com/watch?v=Kdr3fxgRLVU")

    def test_extract_video_id_from_watch_url(self):
        video_id = main.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(video_id, "dQw4w9WgXcQ")

    def test_extract_video_id_from_short_url(self):
        video_id = main.extract_video_id("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(video_id, "dQw4w9WgXcQ")

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

    @patch.dict(
        os.environ,
        {"GOOGLE_API_KEY": "test-key"},
        clear=True,
    )
    @patch("main.genai.Client")
    def test_analyze_transcript_uses_current_sdk_and_formats_output(self, client_cls):
        client = MagicMock()
        response = MagicMock()
        response.text = """
        BEHAVIOR-LEVEL SIGNALS (High WTP Evidence)
        - QUOTE: customer paid for a workaround
        - CATEGORY: Money Spent
        - WTP IMPLICATION: They already spend on this problem.

        PASS 1 SUMMARY
        - Total high-signal moments: 1
        - Dominant pain category: Money Spent
        - Confidence level: High

        CATEGORY B - GATEKEEPER MENTIONS
        - QUOTE: they rely on the marketplace
        - ENTITY NAMED: marketplace
        - DEPENDENCY TYPE: Platform
        - OPERATOR RELATIONSHIP: Dependent
        - GATEKEEPER SIGNAL: Worth investigating.

        COMBINED INTELLIGENCE SUMMARY
        TOP 3 ACTIONABLE SIGNALS ACROSS BOTH PASSES:
        1. Strong buying behavior in Pass 1.

        ONE HYPOTHESIS WORTH TESTING:
        If operators had a better workflow, they would spend to switch.
        """
        client.models.generate_content.return_value = response
        client_cls.return_value = client

        result = main.analyze_transcript_("customer paid for a workaround")

        self.assertIn("PASS 1: WILLINGNESS-TO-PAY SIGNALS", result)
        self.assertIn("PASS 2: FGP PIPELINE INTELLIGENCE", result)
        self.assertIn("- QUOTE: customer paid for a workaround", result)
        self.assertIn("- Highest-signal gatekeeper mention: marketplace (Platform)", result)
        self.assertIn("1. Strong buying behavior in Pass 1.", result)
        client_cls.assert_called_once_with(api_key="test-key")
        client.models.generate_content.assert_called_once()

    @patch("main._spinner")
    @patch("main.analyze_transcript_")
    def test_run_analysis_with_progress_shows_status(self, analyze_mock, spinner_mock):
        analyze_mock.return_value = "analysis"

        with patch("main.show_status") as status_mock:
            result = main.run_analysis_with_progress("transcript")

        self.assertEqual(result, "analysis")
        status_mock.assert_called_once_with(
            "\nTranscript received. Routing analysis request to Gemini..."
        )
        spinner_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
