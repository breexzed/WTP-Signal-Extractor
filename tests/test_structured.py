"""Schema-enforced model output and retries.

Run: uv run python -m unittest discover -s tests -t .
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import main
from contract import EXIT_ANALYSIS_FAILED, EXIT_OK, EXIT_SOURCE_FAILED
from extract import parse_model_output
from model_output import MODEL_OUTPUT_SCHEMA, parse_any, parse_structured_output
from providers.base import ProviderConfig
from retry import MalformedModelOutput, is_transient, with_retries
from tests.test_agent_contract import FULL_TRANSCRIPT
from tests.test_main import SAMPLE_RAW_OUTPUT

# The same analysis as test_main.SAMPLE_RAW_OUTPUT, in the JSON the schema demands.
SAMPLE_JSON = {
    "behavior_signals": [
        {"quote": "We paid for two scheduling tools", "category": "Money Spent",
         "wtp_implication": "They already spend to solve this problem."},
        {"quote": "then abandoned them", "category": "Tool Abandoned",
         "wtp_implication": "Existing tools failed to fit the workflow."}],
    "opinion_signals": [{"quote": "It would be nice if intake was cleaner",
                         "why_low_signal": "This is a preference statement without action."}],
    "pass1_summary": {"total_high_signal_moments": 2, "dominant_pain_category": "Money Spent",
                      "confidence_level": "High"},
    "cascade_indicators": [{"quote": "missing appointments was costing us clients",
                            "layers_broken": "operator -> clients", "cascade_depth": "Two-layer",
                            "build_signal": "Worth building for because clients are directly affected."}],
    "gatekeeper_mentions": [{"quote": "We still depend on Zocdoc because they control intake volume",
                             "entity_named": "Zocdoc", "dependency_type": "Platform",
                             "operator_relationship": "Dependent",
                             "gatekeeper_signal": "This platform controls a key customer-acquisition path."}],
    "position_intelligence": [{"quote": "they mostly care about keeping throughput high", "entity": "Zocdoc",
                               "what_they_protect": "They optimize for throughput and high booking flow.",
                               "confidence": "Medium"}],
    "subniche_culture_signals": [{"quote": "We're not trying to be the cheapest clinic in town",
                                  "subniche_identified": "Premium dental clinic",
                                  "differentiation_claim": "The operator competes on quality rather than price.",
                                  "fgp_use": "Both"}],
    "pass2_summary": {"strongest_cascade_found": "missing appointments was costing us clients (Two-layer)",
                      "highest_signal_gatekeeper_mention": "Zocdoc (platform)",
                      "position_intelligence_confidence": "Medium",
                      "recommended_next_action": "Phase 3 - investigate the booking platform and its incentives."},
    "top_3_actionable_signals": ["Spends and churns tools - Pass 1.", "Client harm cascades - Pass 2.",
                                 "Zocdoc is a gatekeeper - Pass 2."],
    "hypothesis_worth_testing": "If premium clinics could reduce missed appointments without booking "
                                "platforms, they would switch spend toward a dedicated workflow.",
    "source_diagnostics": {"source_type": "operator_interview", "speaker_type": "operator",
                           "phase_fit": "3", "signal_density": "high"},
    "named_entities": [{"name": "Zocdoc", "entity_kind": "platform", "relationship": "dependent",
                        "supporting_quote": "We still depend on Zocdoc because they control intake volume",
                        "confidence": "high"}],
    "gatekeeper_objects": [{"entity": "Zocdoc", "dependency_type": "platform", "gatekeeper_type": "Type4",
                            "operator_relationship": "dependent",
                            "supporting_quote": "We still depend on Zocdoc because they control intake volume",
                            "confidence": "high"}],
    "register_alignment": [{"register": "complaint_register", "matched_signals": 2, "strength": "medium"},
                           {"register": "intermediary_register", "matched_signals": 1, "strength": "low"}],
    "search_language_feedback": {"likely_too_generic": False, "too_vendor_heavy": False, "off_phase": False,
                                 "likely_operator_facing": True, "likely_gatekeeper_facing": False,
                                 "reason": "Operator-facing with named dependency evidence."},
    "diagnostic_notes": ["Strong operator pain with one named platform dependency."],
}
SAMPLE_JSON_TEXT = json.dumps(SAMPLE_JSON)


class HttpError(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


class TranscriptsDisabled(Exception):
    pass


class YouTubeRequestFailed(Exception):
    pass


def no_sleep():
    return patch.dict(os.environ, {"WTP_RETRY_BASE_DELAY": "0", "WTP_MAX_ATTEMPTS": "3"})


class Schema(unittest.TestCase):
    def walk(self, node, path="$"):
        if isinstance(node, dict) and node.get("type") == "object":
            yield path, node
            for key, child in node["properties"].items():
                yield from self.walk(child, f"{path}.{key}")
        elif isinstance(node, dict) and node.get("type") == "array":
            yield from self.walk(node["items"], f"{path}[]")

    def test_every_object_is_strict(self):
        # OpenAI strict mode rejects a schema unless every object lists all
        # properties as required and forbids extras.
        for path, node in self.walk(MODEL_OUTPUT_SCHEMA):
            self.assertEqual(set(node["required"]), set(node["properties"]), path)
            self.assertIs(node["additionalProperties"], False, path)

    def test_fixture_matches_schema_keys(self):
        self.assertEqual(set(SAMPLE_JSON), set(MODEL_OUTPUT_SCHEMA["required"]))


class StructuredParsing(unittest.TestCase):
    def test_json_and_legacy_text_parse_to_the_same_signals(self):
        new = parse_structured_output(SAMPLE_JSON_TEXT)
        old = parse_model_output(SAMPLE_RAW_OUTPUT)
        # The text format kept the model's quote marks and free casing; JSON
        # has neither (enums are fixed). diagnostics.py lowercases anyway.
        def unquote(items):
            return [{k: v.strip('"').lower() for k, v in i.items()} for i in items]

        # Regression: the text parser used to start a record on "ENTITY:", which
        # split each position_intelligence signal (QUOTE then ENTITY) in two.
        for parsed in (old, new):
            self.assertEqual([set(r) for r in parsed["pass2"]["position_intelligence"]],
                             [{"QUOTE", "ENTITY", "WHAT THEY PROTECT", "CONFIDENCE"}])

        for section in ("pass1", "pass2"):
            for key, value in old[section].items():
                if key == "summary":
                    continue
                self.assertEqual(unquote(new[section][key]), unquote(value), f"{section}.{key}")
        self.assertEqual(new["parse_warnings"], [])

    def test_format_detection(self):
        self.assertEqual(parse_any(SAMPLE_JSON_TEXT)[1], "json")
        self.assertEqual(parse_any("```json\n" + SAMPLE_JSON_TEXT + "\n```")[1], "json")
        self.assertEqual(parse_any(SAMPLE_RAW_OUTPUT)[1], "legacy_text")

    def test_missing_section_is_a_warning(self):
        partial = dict(SAMPLE_JSON)
        del partial["gatekeeper_mentions"]
        self.assertIn("Model JSON violates schema at $.gatekeeper_mentions: missing",
                      parse_structured_output(json.dumps(partial))["parse_warnings"])

    def test_schema_violations_are_warnings(self):
        bad = json.loads(SAMPLE_JSON_TEXT)
        bad["behavior_signals"][0]["category"] = "Vibes"
        bad["pass1_summary"]["total_high_signal_moments"] = "two"
        bad["extra"] = 1
        warnings = parse_structured_output(json.dumps(bad))["parse_warnings"]
        self.assertTrue(any("behavior_signals[0].category: 'Vibes' not one of" in w for w in warnings))
        self.assertTrue(any("total_high_signal_moments: expected integer" in w for w in warnings))
        self.assertTrue(any("$.extra: unexpected field" in w for w in warnings))

    def test_not_json_raises_malformed(self):
        with self.assertRaises(MalformedModelOutput):
            parse_structured_output("{not json")


class Providers(unittest.TestCase):
    def test_gemini_sends_the_schema(self):
        with patch("providers.gemini.genai.Client") as client_cls:
            from providers.gemini import GeminiProvider
            client = client_cls.return_value
            client.models.generate_content.return_value = MagicMock(text="{}")
            GeminiProvider(ProviderConfig("gemini", "m", "k")).generate("p", "s", MODEL_OUTPUT_SCHEMA)
            config = client.models.generate_content.call_args.kwargs["config"]
            self.assertEqual(config.response_mime_type, "application/json")
            self.assertEqual(config.response_json_schema, MODEL_OUTPUT_SCHEMA)

    def reply(self, text="{}"):
        return MagicMock(choices=[MagicMock(message=MagicMock(content=text))])

    def test_openai_compatible_uses_chat_completions_with_strict_schema(self):
        with patch("providers.openai_compatible.OpenAI") as client_cls:
            from providers.openai_compatible import OpenAICompatibleProvider
            create = client_cls.return_value.chat.completions.create
            create.return_value = self.reply()
            provider = OpenAICompatibleProvider(ProviderConfig("ollama", "m", "", "http://x"))
            provider.generate("p", "s", MODEL_OUTPUT_SCHEMA)
            fmt = create.call_args.kwargs["response_format"]
            self.assertEqual((fmt["type"], fmt["json_schema"]["strict"]), ("json_schema", True))
            self.assertEqual(fmt["json_schema"]["schema"], MODEL_OUTPUT_SCHEMA)
            self.assertEqual(provider.structured_mode, "json_schema")

    def test_falls_back_to_json_object_when_schema_is_rejected(self):
        import httpx
        from openai import BadRequestError
        rejected = BadRequestError("response_format json_schema not supported",
                                   response=httpx.Response(400, request=httpx.Request("POST", "http://x")),
                                   body=None)
        with patch("providers.openai_compatible.OpenAI") as client_cls:
            from providers.openai_compatible import OpenAICompatibleProvider
            create = client_cls.return_value.chat.completions.create
            create.side_effect = [rejected, self.reply('{"ok": true}')]
            provider = OpenAICompatibleProvider(ProviderConfig("groq", "m", "k", "http://x"))
            self.assertEqual(provider.generate("p", "sys", MODEL_OUTPUT_SCHEMA), '{"ok": true}')
            second = create.call_args_list[1].kwargs
            self.assertEqual(second["response_format"], {"type": "json_object"})
            self.assertIn('"behavior_signals"', second["messages"][0]["content"])  # schema in prompt
            self.assertEqual(provider.structured_mode, "json_object")


class ProviderPresets(unittest.TestCase):
    @patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "LLM_MODEL_NAME": "qwen2.5:7b"}, clear=True)
    def test_ollama_needs_no_key(self):
        config = main.get_provider_config()
        self.assertEqual((config.base_url, config.model_name), ("http://localhost:11434/v1", "qwen2.5:7b"))

    @patch.dict(os.environ, {"LLM_PROVIDER": "groq", "LLM_MODEL_NAME": "m"}, clear=True)
    def test_hosted_preset_names_its_key(self):
        with self.assertRaises(main.UsageError) as ctx:
            main.get_provider_config()
        self.assertIn("GROQ_API_KEY", str(ctx.exception))

    @patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}, clear=True)
    def test_missing_model_says_how_to_find_one(self):
        with self.assertRaises(main.UsageError) as ctx:
            main.get_provider_config()
        self.assertIn("ollama list", str(ctx.exception))

    @patch.dict(os.environ, {"LLM_PROVIDER": "nope"}, clear=True)
    def test_unknown_provider_lists_choices(self):
        with self.assertRaises(main.UsageError) as ctx:
            main.get_provider_config()
        self.assertIn("ollama", str(ctx.exception))


class Retries(unittest.TestCase):
    def test_transient_classification(self):
        for error in (HttpError(429), HttpError(503), TimeoutError(), ConnectionError(),
                      YouTubeRequestFailed(), MalformedModelOutput("x")):
            self.assertTrue(is_transient(error), error)
        for error in (HttpError(400), HttpError(401), HttpError(404), TranscriptsDisabled(), ValueError()):
            self.assertFalse(is_transient(error), error)

    def test_retries_then_succeeds(self):
        calls = iter([HttpError(503), HttpError(429), "done"])

        def flaky():
            item = next(calls)
            if isinstance(item, Exception):
                raise item
            return item

        logs = []
        with no_sleep():
            self.assertEqual(with_retries(flaky, what="t", log=logs.append), ("done", 3))
        self.assertEqual(len(logs), 2)

    def test_permanent_error_is_not_retried(self):
        calls = []

        def bad_key():
            calls.append(1)
            raise HttpError(401)

        with no_sleep(), self.assertRaises(HttpError) as ctx:
            with_retries(bad_key, what="t", log=lambda m: None)
        self.assertEqual((len(calls), ctx.exception.wtp_attempts), (1, 1))


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wtp-structured-"))
        self.transcript = self.tmp / "t.txt"
        self.transcript.write_text(FULL_TRANSCRIPT, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with no_sleep(), redirect_stdout(out), redirect_stderr(err):
            code = main.main(argv + ["--json", "--out-dir", str(self.tmp / "out")])
        return code, json.loads(out.getvalue()), err.getvalue()


class EndToEnd(TempDir):
    def test_json_run_records_format_and_attempts(self):
        with patch("main.call_model", return_value=SAMPLE_JSON_TEXT):
            code, result, _ = self.run_cli(["--transcript-file", str(self.transcript)])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["run"]["output_format"], "json")
        self.assertEqual(result["run"]["attempts"], {"model": 1})
        self.assertEqual(result["evidence"]["verified"], result["evidence"]["total"])
        self.assertEqual(result["diagnostics"]["field_sources"]["source_type"], "llm")

    def test_malformed_reply_gets_a_second_attempt(self):
        with patch("main.call_model", side_effect=["{truncated", SAMPLE_JSON_TEXT]):
            code, result, err = self.run_cli(["--transcript-file", str(self.transcript)])
        self.assertEqual((code, result["run"]["attempts"]["model"]), (EXIT_OK, 2))
        self.assertIn("MalformedModelOutput", err)

    def test_model_gives_up_after_max_attempts(self):
        with patch("main.call_model", side_effect=HttpError(503)) as call:
            code, result, _ = self.run_cli(["--transcript-file", str(self.transcript)])
        self.assertEqual((code, call.call_count), (EXIT_ANALYSIS_FAILED, 3))
        self.assertIn("after 3 attempt(s)", result["error"])
        self.assertEqual(result["run"]["attempts"]["model"], 3)

    def test_youtube_no_captions_fails_fast(self):
        with patch("main.get_transcript_from_url", side_effect=TranscriptsDisabled("off")) as fetch:
            code, result, _ = self.run_cli(["--url", "https://youtu.be/abc123"])
        self.assertEqual((code, fetch.call_count), (EXIT_SOURCE_FAILED, 1))
        self.assertEqual(result["run"]["attempts"], {"transcript": 1})

    def test_youtube_network_error_is_retried(self):
        with patch("main.get_transcript_from_url",
                   side_effect=[YouTubeRequestFailed("502"), FULL_TRANSCRIPT]), \
                patch("main.call_model", return_value=SAMPLE_JSON_TEXT):
            code, result, _ = self.run_cli(["--url", "https://youtu.be/abc123"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["run"]["attempts"], {"transcript": 2, "model": 1})


if __name__ == "__main__":
    unittest.main()
