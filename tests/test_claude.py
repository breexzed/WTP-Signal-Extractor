"""Claude provider: request shape and stop-reason handling. The SDK is mocked
(no credentials on the dev machine; live runs are untested)."""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from wtp import cli
from wtp.model_output import MODEL_OUTPUT_SCHEMA
from wtp.providers.base import ProviderConfig
from wtp.providers.claude import ClaudeProvider, ClaudeRefusal, ClaudeTruncated
from wtp.retry import is_transient


def fake_message(stop_reason="end_turn", text='{"ok": true}', details=None):
    block = MagicMock(type="text", text=text)
    return MagicMock(stop_reason=stop_reason, content=[block], stop_details=details)


class ClaudeRequests(unittest.TestCase):
    def run_generate(self, model, message):
        with patch("wtp.providers.claude.anthropic.Anthropic") as client_cls:
            stream = client_cls.return_value.beta.messages.stream
            stream.return_value.__enter__.return_value.get_final_message.return_value = message
            provider = ClaudeProvider(ProviderConfig("anthropic", model, "sk-test"))
            text = provider.generate("prompt", "system", MODEL_OUTPUT_SCHEMA)
            return text, stream.call_args.kwargs, client_cls.call_args.kwargs

    def test_schema_streaming_and_fallback_on_opus(self):
        text, request, client_kwargs = self.run_generate("claude-opus-5-5", fake_message())
        self.assertEqual(text, '{"ok": true}')
        self.assertEqual(request["output_config"]["format"],
                         {"type": "json_schema", "schema": MODEL_OUTPUT_SCHEMA})
        self.assertEqual(request["output_config"]["effort"], "medium")
        self.assertEqual((request["betas"], request["fallbacks"]),
                         (["server-side-fallback-2026-07-01"], "default"))
        self.assertEqual(client_kwargs["max_retries"], 0)   # wtp.retry owns retries

    def test_no_fallback_param_on_models_that_reject_it(self):
        _, request, _ = self.run_generate("claude-haiku-5-5", fake_message())
        self.assertNotIn("fallbacks", request)
        self.assertNotIn("betas", request)

    def test_refusal_and_truncation_are_permanent_errors(self):
        details = MagicMock(category="cyber", explanation="declined")
        with self.assertRaises(ClaudeRefusal) as ctx:
            self.run_generate("claude-opus-5-5", fake_message("refusal", details=details))
        self.assertIn("cyber", str(ctx.exception))
        self.assertFalse(is_transient(ctx.exception))
        with self.assertRaises(ClaudeTruncated) as ctx:
            self.run_generate("claude-opus-5-5", fake_message("max_tokens"))
        self.assertFalse(is_transient(ctx.exception))


class ClaudePreset(unittest.TestCase):
    @patch.dict(os.environ, {"LLM_PROVIDER": "anthropic"}, clear=True)
    def test_defaults_and_key_is_optional(self):
        config = cli.get_provider_config()      # an `ant auth login` profile can stand in for a key
        self.assertEqual((config.model_name, config.api_key), ("claude-opus-5-5", ""))

    @patch.dict(os.environ, {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "k"}, clear=True)
    def test_routes_to_claude_provider(self):
        with patch("wtp.cli.ClaudeProvider") as claude:
            cli.get_llm_provider()
        claude.assert_called_once()


if __name__ == "__main__":
    unittest.main()
