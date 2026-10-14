"""Failed runs say what failed and what to do next, briefly (from a real
RequestBlocked run on 2026-10-14 that printed ~60 lines and the error twice)."""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from wtp import cli
from wtp.contract import EXIT_ANALYSIS_FAILED, EXIT_SOURCE_FAILED


class RequestBlocked(Exception):
    """Same name and message shape as youtube_transcript_api's."""


ESSAY = ("\nCould not retrieve a transcript for the video https://www.youtube.com/watch?v=x! "
         "This is most likely caused by:\n\nYouTube is blocking requests from your IP.\n" + "more\n" * 15)


class HttpError(Exception):
    def __init__(self, code):
        super().__init__(f"{code} error")
        self.code = code


class Failures(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wtp-fail-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"WTP_RETRY_BASE_DELAY": "0"}), redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv + ["--out-dir", str(self.tmp)])
        return code, out.getvalue(), err.getvalue()

    def test_youtube_block_json(self):
        with patch("wtp.cli.get_transcript_from_url", side_effect=RequestBlocked(ESSAY)) as fetch:
            code, out, err = self.run_cli(["--url", "https://youtu.be/abc123", "--json"])
        result = json.loads(out)
        self.assertEqual((code, fetch.call_count), (EXIT_SOURCE_FAILED, 1))   # never retried
        self.assertEqual(result["parse_warnings"], [])                       # not a parse problem
        self.assertIn("--transcript-file", result["next_step"])
        self.assertIn("WTP_YT_PROXY", result["next_step"])
        self.assertIn("YouTube is blocking", result["error"])                # full text kept in JSON
        self.assertLessEqual(len(err.strip().splitlines()), 4)               # stderr: no essay
        self.assertIn("Next:", err)

    def test_youtube_block_human_report_is_short(self):
        with patch("wtp.cli.get_transcript_from_url", side_effect=RequestBlocked(ESSAY)):
            _, out, _ = self.run_cli(["--url", "https://youtu.be/abc123"])
        self.assertIn("NEXT STEP", out)
        self.assertNotIn("None found.", out)
        self.assertLess(out.count("\n"), 40)

    def test_model_not_found_names_the_fix(self):
        path = self.tmp / "t.txt"
        path.write_text("we paid for two tools and dropped them")
        with patch("wtp.cli.call_model", side_effect=HttpError(404)):
            code, out, _ = self.run_cli(["--transcript-file", str(path), "--json"])
        self.assertEqual(code, EXIT_ANALYSIS_FAILED)
        self.assertIn("LLM_MODEL_NAME", json.loads(out)["next_step"])

    def test_proxy_is_passed_to_youtube_and_never_echoed(self):
        secret = "http://user:hunter2@proxy.example:8080"
        with patch.dict(os.environ, {"WTP_YT_PROXY": secret}), \
                patch("wtp.cli.YouTubeTranscriptApi") as api:
            api.return_value.fetch.return_value = [{"text": "hi"}]
            cli.get_transcript_from_url("https://youtu.be/abc123")
            config = api.call_args.kwargs["proxy_config"]
            self.assertEqual(config.http_url, secret)
            code, out, _ = self.run_cli(["--check"])
        self.assertTrue(json.loads(out)["youtube_proxy_set"])
        self.assertNotIn("hunter2", out)


if __name__ == "__main__":
    unittest.main()
