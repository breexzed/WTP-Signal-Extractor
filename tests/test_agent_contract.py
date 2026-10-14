"""The contract an AI agent relies on: discoverable, non-interactive, parseable,
honest exit codes, verifiable evidence, offline replay.

Run: uv run python -m unittest discover -s tests -t .
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import main
from aggregate import aggregate_source_results
from contract import (
    EXIT_ANALYSIS_FAILED,
    EXIT_DEGRADED,
    EXIT_OK,
    EXIT_SOURCE_FAILED,
    EXIT_USAGE,
    SCHEMA_VERSION,
)
from diagnostics import build_diagnostics, extract_recommended_phase
from extract import parse_model_output
from tests.test_main import SAMPLE_RAW_OUTPUT
from verify import verify_quotes

REPO = Path(__file__).resolve().parent.parent

# Contains every quote in SAMPLE_RAW_OUTPUT, so a clean run verifies all of them.
FULL_TRANSCRIPT = (
    "Honestly we paid for two scheduling tools and then abandoned them. "
    "It would be nice if intake was cleaner. Missing appointments was costing us clients. "
    "We still depend on Zocdoc because they control intake volume, and "
    "they mostly care about keeping throughput high. "
    "We're not trying to be the cheapest clinic in town."
)


def run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    """Run main.py the way an agent does: a subprocess, no terminal on stdin."""
    return subprocess.run(
        [sys.executable, str(REPO / "main.py"), *args],
        input=stdin, capture_output=True, text=True, timeout=60, cwd=REPO,
        stdin=None if stdin is not None else subprocess.DEVNULL,
    )


def run_in_process(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main.main(argv)
    return code, out.getvalue(), err.getvalue()


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wtp-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name: str, text: str) -> Path:
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path


class Discoverability(unittest.TestCase):
    def test_describe_is_complete_json(self):
        p = run_cli("--describe")
        self.assertEqual(p.returncode, EXIT_OK, p.stderr)
        doc = json.loads(p.stdout)
        for key in ("exit_codes", "flags", "vocabularies", "domain", "result_fields",
                    "result_skeleton", "manifest_example", "agent_quickstart", "environment"):
            self.assertIn(key, doc)
        flags = {f["flag"] for f in doc["flags"]}
        self.assertTrue({"--url", "--transcript-file", "--session", "--replay", "--json",
                         "--check", "--describe"} <= flags)
        # Every top-level result field is explained to the agent.
        skeleton_keys = set(doc["result_skeleton"]) - {"schema_version"}
        self.assertEqual(skeleton_keys - set(doc["result_fields"]), set())
        self.assertEqual(doc["schema_version"], SCHEMA_VERSION)

    def test_versions_agree(self):
        import tomllib
        from contract import TOOL_VERSION
        with open(REPO / "pyproject.toml", "rb") as f:
            self.assertEqual(tomllib.load(f)["project"]["version"], TOOL_VERSION)

    def test_help_points_agents_to_describe(self):
        p = run_cli("--help")
        self.assertIn("--describe", p.stdout)
        self.assertIn("Exit codes", p.stdout)

    @patch.dict("os.environ", {"LLM_PROVIDER": "gemini"}, clear=True)
    def test_check_without_key_is_usage_error_and_never_leaks_keys(self):
        with patch("main.Path.exists", return_value=False):
            code, out, _ = run_in_process(["--check"])
        doc = json.loads(out)
        self.assertEqual(code, EXIT_USAGE)
        self.assertFalse(doc["api_key_present"])
        self.assertIn("GEMINI_API_KEY", doc["config_error"])

    @patch.dict("os.environ", {"GEMINI_API_KEY": "secret-value-123"}, clear=True)
    def test_check_with_key(self):
        code, out, _ = run_in_process(["--check"])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(json.loads(out)["api_key_present"])
        self.assertNotIn("secret-value-123", out)


class NeverHangs(unittest.TestCase):
    def test_no_input_without_terminal_exits_usage(self):
        p = run_cli()
        self.assertEqual(p.returncode, EXIT_USAGE)
        self.assertIn("--transcript-file", p.stderr)
        self.assertEqual(p.stdout, "")

    def test_two_inputs_is_usage_error(self):
        p = run_cli("--url", "https://youtu.be/x", "--transcript-file", "f.txt")
        self.assertEqual(p.returncode, EXIT_USAGE)
        self.assertIn("Pick one input", p.stderr)


class JsonContract(TempDirTest):
    def analyze(self, transcript: str, raw: str = SAMPLE_RAW_OUTPUT, extra=()):
        path = self.write("t.txt", transcript)
        with patch("main.call_model", return_value=raw):
            return run_in_process(["--transcript-file", str(path), "--json",
                                   "--out-dir", str(self.tmp / "out"), *extra])

    def test_stdout_is_exactly_one_json_document(self):
        code, out, err = self.analyze(FULL_TRANSCRIPT)
        result = json.loads(out)                      # raises if anything else is on stdout
        self.assertEqual(code, EXIT_OK, err)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertEqual(result["evidence"]["not_found"], 0)
        self.assertEqual(result["run"]["mode"], "live")
        self.assertEqual(len(result["run"]["prompt_sha256"]), 64)
        self.assertIn("Calling", err)                 # progress went to stderr

    def test_artifacts_exist_and_transcript_is_saved(self):
        _, out, _ = self.analyze(FULL_TRANSCRIPT)
        result = json.loads(out)
        for key in ("text_path", "json_path", "transcript_path"):
            self.assertTrue(Path(result["artifacts"][key]).is_file(), key)
        self.assertEqual(Path(result["source"]["transcript_path"]).read_text(), FULL_TRANSCRIPT)
        saved = json.loads(Path(result["artifacts"]["json_path"]).read_text())
        self.assertEqual(saved["artifacts"], result["artifacts"])

    def test_invented_quote_degrades_the_run(self):
        code, out, _ = self.analyze("We paid for two tools and still depend on Zocdoc.")
        result = json.loads(out)
        self.assertEqual(code, EXIT_DEGRADED)
        self.assertEqual(result["status"], "degraded")
        self.assertGreater(result["evidence"]["not_found"], 0)

    def test_stdin_transcript(self):
        with patch("main.call_model", return_value=SAMPLE_RAW_OUTPUT), \
                patch("sys.stdin", io.StringIO(FULL_TRANSCRIPT)):
            code, out, _ = run_in_process(["--transcript-file", "-", "--json",
                                           "--out-dir", str(self.tmp)])
        self.assertEqual((code, json.loads(out)["source"]["transcript_chars"]),
                         (EXIT_OK, len(FULL_TRANSCRIPT)))

    def test_provider_error_is_data_not_a_crash(self):
        path = self.write("t.txt", FULL_TRANSCRIPT)
        with patch("main.call_model", side_effect=TimeoutError("deadline exceeded")):
            code, out, _ = run_in_process(["--transcript-file", str(path), "--json",
                                           "--out-dir", str(self.tmp)])
        result = json.loads(out)
        self.assertEqual(code, EXIT_ANALYSIS_FAILED)
        self.assertEqual(result["status"], "analysis_failed")
        self.assertIn("TimeoutError: deadline exceeded", result["error"])

    def test_transcript_fetch_failure(self):
        with patch("main.get_transcript_from_url", side_effect=RuntimeError("Subtitles are disabled")):
            code, out, _ = run_in_process(["--url", "https://youtu.be/abc123", "--json",
                                           "--out-dir", str(self.tmp)])
        result = json.loads(out)
        self.assertEqual((code, result["status"]), (EXIT_SOURCE_FAILED, "transcript_failed"))
        self.assertIn("Subtitles are disabled", result["error"])

    def test_session_exit_is_worst_source(self):
        manifest = self.write("m.json", json.dumps({"session_id": "s", "sources": [
            {"source_id": "good", "transcript": FULL_TRANSCRIPT},
            {"source_id": "empty"},
        ]}))
        with patch("main.call_model", return_value=SAMPLE_RAW_OUTPUT):
            code, out, _ = run_in_process(["--session", str(manifest), "--json",
                                           "--out-dir", str(self.tmp)])
        session = json.loads(out)
        self.assertEqual(code, EXIT_SOURCE_FAILED)
        self.assertEqual(session["status_counts"], {"ok": 1, "transcript_failed": 1})
        self.assertTrue(all(Path(s["json_path"]).is_file() for s in session["sources"]))


class Replay(TempDirTest):
    def test_replay_never_calls_the_model(self):
        raw = self.write("raw.txt", SAMPLE_RAW_OUTPUT)
        transcript = self.write("t.txt", FULL_TRANSCRIPT)
        with patch("main.call_model", side_effect=AssertionError("network call in replay")):
            code, out, _ = run_in_process(["--replay", str(raw), "--transcript-file", str(transcript),
                                           "--json", "--out-dir", str(self.tmp)])
        result = json.loads(out)
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["run"]["mode"], "replay")
        self.assertEqual(result["evidence"]["verified"], result["evidence"]["total"])

    def test_replay_without_transcript_says_quotes_unchecked(self):
        raw = self.write("raw.txt", SAMPLE_RAW_OUTPUT)
        code, out, _ = run_in_process(["--replay", str(raw), "--json", "--out-dir", str(self.tmp)])
        result = json.loads(out)
        self.assertEqual(code, EXIT_OK)
        self.assertFalse(result["evidence"]["checked"])


class Evidence(unittest.TestCase):
    def check(self, quote: str, transcript: str) -> str:
        ev = verify_quotes({"pass1": {"behavior_signals": [{"QUOTE": quote}]}}, transcript)
        return ev["items"][0]["status"]

    def test_quote_statuses(self):
        t = "So yeah, we paid for two scheduling tools last year — and then we abandoned both of them."
        self.assertEqual(self.check('"We paid for two scheduling tools"', t), "verified")
        self.assertEqual(self.check("we paid for 2 scheduling tools last year and then we abandoned both", t),
                         "approximate")
        self.assertEqual(self.check("our biggest cost is insurance paperwork", t), "not_found")

    def test_repeated_phrase_does_not_misplace_the_quote(self):
        # Real case (C4eyhRQdD_s): "I had to be like" occurs twice; anchoring on
        # the first one hid the real match and called a real quote not_found.
        t = ("I had to be like, don't you know who I am? You know, I'm just a local guy. "
             "Later on I had to just be like, I'm sorry, yo.")
        self.assertEqual(self.check("I had to be like, I'm sorry, yo.", t), "approximate")

    def test_stitched_quote_is_not_called_invented(self):
        # Real case (C4eyhRQdD_s): two real sentences, joined in reverse order.
        t = ("People have a lot of trouble canceling on their contract. I tried twice. "
             "Then I called support and waited an hour. Canceling your contract is like near impossible.")
        q = "Canceling your contract is like near impossible. People have a lot of trouble canceling on their contract."
        self.assertEqual(self.check(q, t), "stitched")
        self.assertEqual(self.check("Canceling is easy. Support answered at once and refunded me.", t), "not_found")


class HonestDiagnostics(unittest.TestCase):
    def test_heuristics_run_when_model_omits_diagnostics(self):
        raw = SAMPLE_RAW_OUTPUT.split("SOURCE DIAGNOSTICS")[0]
        d = build_diagnostics(parse_model_output(raw), "we paid for it, our workflow broke", {})
        self.assertEqual(d["field_sources"]["source_type"], "heuristic")
        self.assertEqual(d["source_type"], "operator_interview")
        self.assertNotEqual(d["phase_fit"], "unknown")

    def test_model_answers_are_labelled_llm(self):
        d = build_diagnostics(parse_model_output(SAMPLE_RAW_OUTPUT), FULL_TRANSCRIPT, {})
        self.assertEqual(d["field_sources"]["source_type"], "llm")
        self.assertEqual(d["field_sources"]["recommended_next_phase"], "llm")

    def test_phase_prefers_explicit_phase_over_stray_digits(self):
        self.assertEqual(extract_recommended_phase("Run 2 more interviews, then Phase 3.5 work"), "3.5")
        self.assertEqual(extract_recommended_phase("Feeds phase 0 framing"), "0")

    def test_session_register_strength_is_kept(self):
        def result(strength):
            return {"source": {"source_id": "x", "source_type": "unknown"},
                    "provenance": {"query_used": None},
                    "pass1": {"summary": {"total_high_signal_moments": 0}},
                    "pass2": {"gatekeeper_mentions": [], "cascade_indicators": []},
                    "diagnostics": {"register_alignment": [{"register": "complaint_register",
                                                            "matched_signals": 1, "strength": strength}],
                                    "gatekeepers": [], "named_entities": [],
                                    "recommended_next_phase": "1",
                                    "search_language_feedback": {"likely_too_generic": False,
                                                                 "too_vendor_heavy": False}}}
        agg = aggregate_source_results([result("low"), result("high")])
        self.assertEqual(agg["register_performance"][0]["strength"], "high")


if __name__ == "__main__":
    unittest.main()
