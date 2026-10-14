"""WTP Signal Extractor CLI.

Built to be driven by an AI agent as well as a person:
- `--describe` prints the whole contract (flags, exit codes, vocabularies, output shape, domain).
- `--json` puts exactly one JSON document on stdout; progress and errors go to stderr.
- Exit codes say what happened (see contract.EXIT_CODES); nothing fails silently.
- Never prompts for input unless stdin is a terminal and no input flag was given.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi

from wtp import contract, install
from wtp.aggregate import build_session_result
from wtp.diagnostics import build_diagnostics
from wtp.model_output import MODEL_OUTPUT_SCHEMA, parse_any
from wtp.prompt import SYSTEM_PROMPT
from wtp.providers.base import ProviderConfig
from wtp.providers.gemini import GeminiProvider
from wtp.providers.claude import DEFAULT_MODEL as DEFAULT_CLAUDE_MODEL, ClaudeProvider
from wtp.providers.openai_compatible import OpenAICompatibleProvider
from wtp.render import render_result, render_session_report, safe_console_text
from wtp.schemas import merge_result
from wtp.session_store import sanitize_token, write_artifacts, write_session_artifacts
from wtp.retry import status_code, with_retries
from wtp.verify import verify_quotes

# gemini-2.5-flash now returns 404 "no longer available to new users" (checked
# 2026-10-14); the API names gemini-3.8-flash as its replacement.
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
CONFIG_FILES = install.load_config()  # before anything reads os.environ
DEFAULT_OUTPUT_DIR = str(install.data_dir() / "runs")
DEFAULT_REPORTS_DIR = str(install.data_dir() / "sessions")
SESSION_CONTEXT_FIELDS = [
    "vertical",
    "operator_type",
    "targeted_subniche",
    "fgp_phase",
    "gatekeeper_type",
    "currency_window",
    "session_date",
    "prior_loop_map_phase",
]
PROMPT_SHA256 = hashlib.sha256(
    (SYSTEM_PROMPT + json.dumps(MODEL_OUTPUT_SCHEMA, sort_keys=True)).encode("utf-8")
).hexdigest()



class UsageError(RuntimeError):
    """Bad flags, config or input file. Exits with contract.EXIT_USAGE."""


def log(message: str) -> None:
    """Progress and errors. Always stderr, so stdout stays parseable."""
    print(message, file=sys.stderr, flush=True)


# Kept for callers of the old name.
show_status = log


# ---------------------------------------------------------------- provider config

def normalize_youtube_input(text: str) -> str:
    text = text.strip()
    match = re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s)>,]+", text)
    if match:
        return match.group(0).rstrip(".,]")
    return text


# One row per provider. Anything that speaks the OpenAI Chat Completions API
# works through "openai_compatible" with LLM_BASE_URL; the rest are shortcuts.
# base URLs checked 2026-10-14 (Groq/OpenAI 401 without a key, OpenRouter 200,
# Ollama local). Model names go stale, so only Gemini has a default.
PROVIDERS: dict[str, dict[str, object]] = {
    "gemini": {"kind": "gemini", "key_env": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEYS"),
               "model_env": ("GEMINI_MODEL_NAME",), "default_model": DEFAULT_GEMINI_MODEL,
               "free": "Google AI Studio free tier (rate limited)"},
    "anthropic": {"kind": "claude", "key_env": ("ANTHROPIC_API_KEY",), "key_optional": True,
                  "model_env": ("ANTHROPIC_MODEL",), "default_model": DEFAULT_CLAUDE_MODEL,
                  "free": "paid; key optional if `ant auth login` was run"},
    "ollama": {"kind": "openai", "base_url": "http://localhost:11434/v1", "key_env": (),
               "model_env": ("OLLAMA_MODEL",), "free": "local, no key; `ollama list` shows models"},
    "llamacpp": {"kind": "openai", "base_url": "http://localhost:8080/v1", "key_env": (),
                 "model_env": (), "free": "local llama-server, no key"},
    "groq": {"kind": "openai", "base_url": "https://api.groq.com/openai/v1",
             "key_env": ("GROQ_API_KEY",), "model_env": (), "free": "free tier (rate limited)"},
    "openrouter": {"kind": "openai", "base_url": "https://openrouter.ai/api/v1",
                   "key_env": ("OPENROUTER_API_KEY",), "model_env": (),
                   "free": "has ':free' models (rate limited)"},
    "openai": {"kind": "openai", "base_url": "https://api.openai.com/v1",
               "key_env": ("OPENAI_API_KEY",), "model_env": (), "free": "paid"},
    "openai_compatible": {"kind": "openai", "key_env": ("OPENAI_COMPATIBLE_API_KEY",),
                          "model_env": ("OPENAI_COMPATIBLE_MODEL_NAME",),
                          "free": "any server: set LLM_BASE_URL"},
}


def get_provider_name() -> str:
    return os.getenv("LLM_PROVIDER", "gemini").strip().lower() or "gemini"


def provider_preset(provider_name: str) -> dict[str, object]:
    if provider_name not in PROVIDERS:
        raise UsageError(f"Unsupported provider '{provider_name}'. Supported: {', '.join(PROVIDERS)}.")
    return PROVIDERS[provider_name]


def first_env(names) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def get_model_name(provider_name: str) -> str | None:
    preset = PROVIDERS.get(provider_name, {})
    return (first_env(preset.get("model_env", ())) or os.getenv("LLM_MODEL_NAME")
            or preset.get("default_model"))


def get_provider_config() -> ProviderConfig:
    provider_name = get_provider_name()
    preset = provider_preset(provider_name)
    model = get_model_name(provider_name)
    if not model:
        hint = " (run `ollama list`)" if provider_name == "ollama" else ""
        raise UsageError(f"No model set for provider '{provider_name}'. Set LLM_MODEL_NAME{hint}.")

    key_env = preset["key_env"]
    api_key = first_env(key_env) or os.getenv("LLM_API_KEY") or ""
    if key_env and not api_key and not preset.get("key_optional"):
        user_env = install.config_dir() / ".env"
        raise UsageError(f"Missing API key for '{provider_name}'. Add `{key_env[0]}=...` to {user_env} "
                         f"(or export {' / '.join(key_env)} or LLM_API_KEY). "
                         "No key needed for local models: LLM_PROVIDER=ollama.")

    if preset["kind"] == "gemini":
        return ProviderConfig(provider_name=provider_name, model_name=model, api_key=api_key)
    if preset["kind"] == "claude":
        return ProviderConfig(provider_name=provider_name, model_name=model, api_key=api_key,
                              base_url=os.getenv("LLM_BASE_URL"))
    base_url = (os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_COMPATIBLE_BASE_URL")
                or preset.get("base_url"))
    if not base_url:
        raise UsageError(f"Missing base URL for '{provider_name}'. Set LLM_BASE_URL.")
    return ProviderConfig(provider_name=provider_name, model_name=model, api_key=api_key,
                          base_url=str(base_url))


def get_llm_provider():
    config = get_provider_config()
    kind = PROVIDERS[config.provider_name]["kind"]
    if kind == "gemini":
        return GeminiProvider(config)
    if kind == "claude":
        return ClaudeProvider(config)
    return OpenAICompatibleProvider(config)


def preflight() -> dict[str, object]:
    """Everything an agent needs to know before spending an API call. No network."""
    checks: dict[str, object] = {"tool_version": contract.TOOL_VERSION,
                                 "schema_version": contract.SCHEMA_VERSION,
                                 "cwd": os.getcwd(),
                                 "config_files_loaded": CONFIG_FILES,
                                 "config_dir": str(install.config_dir()),
                                 "data_dir": str(install.data_dir()),
                                 "installed_as_uv_tool": install.installed_as_uv_tool()}
    provider_name = get_provider_name()
    checks["provider"] = provider_name
    checks["model"] = get_model_name(provider_name)
    try:
        config = get_provider_config()
        checks["api_key_present"] = bool(config.api_key)
        checks["base_url"] = config.base_url
        checks["config_error"] = None
    except UsageError as error:
        checks["api_key_present"] = False
        checks["config_error"] = str(error)
    probe = install.data_dir()
    while not probe.exists() and probe != probe.parent:  # stop at / even if nothing exists
        probe = probe.parent
    checks["data_dir_writable"] = os.access(probe, os.W_OK)
    checks["youtube_proxy_set"] = bool(os.getenv("WTP_YT_PROXY"))  # never the URL: it may hold a password
    checks["ok"] = checks["config_error"] is None
    return checks


# ---------------------------------------------------------------- input sources

def extract_video_id(url: str) -> str:
    url = normalize_youtube_input(url)
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

    if "youtu.be" in netloc:
        return parsed.path.strip("/")

    if "youtube.com" in netloc:
        query = parse_qs(parsed.query)
        if "v" in query:
            return query["v"][0]

    raise ValueError(f"Not a YouTube video URL: {url!r} (expected youtu.be/ID or youtube.com/watch?v=ID)")


def youtube_proxy_config():
    """WTP_YT_PROXY=http://user:pass@host:port routes caption fetches through a proxy
    (the documented way around YouTube IP blocks)."""
    proxy = os.getenv("WTP_YT_PROXY")
    if not proxy:
        return None
    from youtube_transcript_api.proxies import GenericProxyConfig
    return GenericProxyConfig(http_url=proxy, https_url=proxy)


def get_transcript_from_url(url: str) -> str:
    video_id = extract_video_id(url)
    transcript_data = YouTubeTranscriptApi(proxy_config=youtube_proxy_config()).fetch(video_id)
    return " ".join(
        entry.text if hasattr(entry, "text") else entry["text"]
        for entry in transcript_data
    )


def fetch_transcript(url: str) -> tuple[str, int]:
    """(transcript, attempts). Retries network/5xx; fails fast on no captions or blocks."""
    return with_retries(lambda: get_transcript_from_url(url), what="YouTube transcript", log=log)


def read_text_input(path: str) -> str:
    """Read a file, or stdin when path is '-'."""
    if path == "-":
        return sys.stdin.read()
    file_path = Path(path)
    if not file_path.is_file():
        raise UsageError(f"File not found: {file_path}")
    return file_path.read_text(encoding="utf-8")


def load_urls_from_file(path: str) -> list[str]:
    file_path = Path(path)
    if not file_path.exists():
        raise UsageError(f"URLs file not found: {file_path}")

    urls = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        urls.append(normalize_youtube_input(stripped))
    return urls


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def collect_batch_urls(args: argparse.Namespace) -> list[str]:
    urls = [normalize_youtube_input(url) for url in (args.urls or []) if url.strip()]
    if args.urls_file:
        urls.extend(load_urls_from_file(args.urls_file))
    return dedupe_preserve_order(urls)


def load_session_manifest(path: str) -> dict[str, object]:
    file_path = Path(path)
    if not file_path.exists():
        raise UsageError(f"Session manifest not found: {file_path}")

    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise UsageError(f"Session manifest is not valid JSON: {error}") from error

    if not isinstance(payload, dict):
        raise UsageError("Session manifest must be a JSON object. See `--describe` manifest_example.")

    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise UsageError("Session manifest must include a 'sources' list. See `--describe` manifest_example.")

    return payload


# ---------------------------------------------------------------- records

def build_source_id(input_type: str, video_id: str | None = None) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")  # file names add -2.. on collision
    if video_id:
        return f"{input_type}-{video_id}-{timestamp}"
    return f"{input_type}-{timestamp}"


def build_session_id() -> str:
    return datetime.now().strftime("session-%Y%m%d-%H%M%S")


def build_source_record(
    *,
    source_id: str,
    url: str | None,
    video_id: str | None,
    input_type: str,
    transcript_status: str,
    source_type: str = "unknown",
    speaker_type: str = "unknown",
) -> dict[str, str | None]:
    return {
        "source_id": source_id,
        "url": url,
        "video_id": video_id,
        "input_type": input_type,
        "transcript_status": transcript_status,
        "source_type": source_type,
        "speaker_type": speaker_type,
    }


def default_provenance() -> dict[str, str | None]:
    return {
        "origin_cluster_id": None,
        "origin_register": None,
        "query_used": None,
    }


def default_session_context() -> dict[str, str | None]:
    return {field: None for field in SESSION_CONTEXT_FIELDS}


def normalize_optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_provenance(value: dict[str, object] | None) -> dict[str, str | None]:
    provenance = default_provenance()
    for key in provenance:
        raw_value = None if not isinstance(value, dict) else value.get(key)
        provenance[key] = normalize_optional_string(raw_value)
    return provenance


def normalize_session_context(value: dict[str, object] | None) -> dict[str, str | None]:
    session_context = default_session_context()
    for field in session_context:
        raw_value = None if not isinstance(value, dict) else value.get(field)
        session_context[field] = normalize_optional_string(raw_value)
    return session_context


def build_reports_output_dir(session_id: str) -> Path:
    return Path(DEFAULT_REPORTS_DIR) / sanitize_token(session_id, fallback="session")


def run_metadata(started: float, mode: str, output_format: str, attempts: dict[str, int]) -> dict[str, object]:
    provider = get_provider_name()
    return {
        "tool_version": contract.TOOL_VERSION,
        "schema_version": contract.SCHEMA_VERSION,
        "mode": mode,  # "live" (model called) or "replay" (saved model output re-parsed)
        "output_format": output_format,  # "json" (schema-enforced) or "legacy_text" (old runs)
        # json_schema = server enforced the schema; json_object = only JSON was enforced
        # and the schema was checked locally (see parse_warnings for violations).
        "structured_mode": LAST_STRUCTURED_MODE if mode == "live" else None,
        "attempts": attempts,
        "provider": provider if mode == "live" else None,
        "model": get_model_name(provider) if mode == "live" else None,
        "prompt_sha256": PROMPT_SHA256,
        "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "duration_s": round(time.time() - started, 3),
    }


def result_status(result: dict[str, object]) -> str:
    if result["parse_warnings"] or result["evidence"].get("not_found"):
        return "degraded"
    return "ok"


# ---------------------------------------------------------------- analysis

def _spinner(stop_event: threading.Event, label: str) -> None:
    frames = "|/-\\"
    index = 0
    while not stop_event.is_set():
        sys.stderr.write(f"\r{label} {frames[index % len(frames)]}")
        sys.stderr.flush()
        index += 1
        time.sleep(0.12)
    sys.stderr.write(f"\r{label} done\n")
    sys.stderr.flush()


# How the last reply was constrained (see providers): json_schema | json_object.
LAST_STRUCTURED_MODE: str | None = None


def call_model(transcript: str) -> str:
    global LAST_STRUCTURED_MODE
    prompt = f"Analyze this transcript for market intelligence signals:\n\n{transcript}"
    provider = get_llm_provider()
    text = provider.generate(prompt, SYSTEM_PROMPT, MODEL_OUTPUT_SCHEMA)
    mode = getattr(provider, "structured_mode", None)
    LAST_STRUCTURED_MODE = mode if isinstance(mode, str) else None
    return text


def call_and_parse(transcript: str) -> tuple[str, dict, str, int]:
    """Model call + parse, retried together: a reply that is not valid JSON
    (MalformedModelOutput) gets another attempt, like a 503 does."""
    global LAST_STRUCTURED_MODE
    LAST_STRUCTURED_MODE = None  # never report a previous source's mode

    def attempt():
        raw = call_model(transcript)
        parsed, output_format = parse_any(raw)
        return raw, parsed, output_format
    (raw, parsed, output_format), attempts = with_retries(attempt, what="Model call", log=log)
    return raw, parsed, output_format, attempts


def analyze_transcript_to_result(
    transcript: str,
    source: dict[str, str | None],
    provenance: dict[str, str | None],
    raw_output: str | None = None,
) -> dict[str, object]:
    """Model call (or replay of saved output) -> parse -> diagnose -> verify quotes."""
    started = time.time()
    attempts = dict(source.pop("_attempts", None) or {})
    if raw_output is None:
        mode = "live"
        raw_output, parsed, output_format, attempts["model"] = call_and_parse(transcript)
    else:
        mode = "replay"
        parsed, output_format = parse_any(raw_output)
    diagnostics = build_diagnostics(parsed, transcript, provenance)
    source["source_type"] = diagnostics.pop("source_type")
    source["speaker_type"] = diagnostics.pop("speaker_type")
    source["transcript_chars"] = len(transcript)

    result = merge_result(
        source=source,
        provenance=provenance,
        pass1=parsed["pass1"],
        pass2=parsed["pass2"],
        diagnostics=diagnostics,
        combined_summary=parsed["combined_summary"],
        parse_warnings=parsed["parse_warnings"],
        raw_output=parsed["raw_output"],
    )
    result["evidence"] = verify_quotes(result, transcript)
    result["status"] = result_status(result)
    result["run"] = run_metadata(started, mode, output_format, attempts)
    return result


TRANSCRIPT_ADVICE = {
    ("RequestBlocked", "IpBlocked"):
        "YouTube is blocking caption requests from this IP (not retried: retrying extends blocks). "
        "Wait a few hours, pass the transcript with --transcript-file, or set WTP_YT_PROXY=http://user:pass@host:port.",
    ("TranscriptsDisabled", "NoTranscriptFound"):
        "This video has no captions wtp can fetch. Get a transcript another way and use --transcript-file.",
    ("VideoUnavailable", "VideoUnplayable", "InvalidVideoId", "AgeRestricted", "ValueError"):
        "Check the URL: the video is unavailable, restricted, or not a YouTube video link.",
}


def next_step_for(error: BaseException | None, status: str) -> str:
    """What to do next, in wtp's terms: the action, not the library's essay."""
    names = {cls.__name__ for cls in type(error).__mro__} if error else set()
    code = status_code(error) if error else None
    if status == "transcript_failed":
        for keys, advice in TRANSCRIPT_ADVICE.items():
            if names & set(keys):
                return advice
        return "Try again later, or pass the transcript with --transcript-file."
    if code in (401, 403) or "AuthenticationError" in names:
        return "The API key was rejected. Run `wtp --check` and fix the key in ~/.config/wtp/.env."
    if code == 404 or "NotFoundError" in names:
        return "The model name was not found. Set LLM_MODEL_NAME (or GEMINI_MODEL_NAME) to a current model."
    if code == 429:
        return "Rate limit or quota. Wait, or switch provider (LLM_PROVIDER=ollama runs locally with no quota)."
    if code is not None and code >= 500:
        return "The provider is overloaded or down. Wait a few minutes or set another model/provider."
    if "ClaudeRefusal" in names:
        return "Claude declined this transcript. Try another provider."
    if "MalformedModelOutput" in names:
        return "The model kept returning invalid JSON. Try a larger model."
    return "Read `error`, run `wtp --check`, then retry or switch provider."


def short_error(error: BaseException) -> str:
    """Type plus the first line: libraries put whole essays in exception messages."""
    first = next((line.strip() for line in str(error).splitlines() if line.strip()), "")
    return f"{type(error).__name__}: {first}"[:300]


def build_failure_result(
    source: dict[str, str | None],
    provenance: dict[str, str | None],
    warning: str,
    status: str = "analysis_failed",
    error: BaseException | None = None,
) -> dict[str, object]:
    result = merge_result(
        source=source,
        provenance=provenance,
        pass1={},
        pass2={},
        diagnostics={},
        combined_summary={},
        parse_warnings=[],      # nothing was parsed; the failure lives in `error`
        raw_output=None,
    )
    result["status"] = status
    result["error"] = warning
    result["next_step"] = next_step_for(error, status)
    result["evidence"]["reason"] = "Analysis did not run."
    return result


def run_analysis_with_progress(
    transcript: str,
    source: dict[str, str | None],
    provenance: dict[str, str | None],
    raw_output: str | None = None,
) -> dict[str, object]:
    if raw_output is not None:
        log("Replaying saved model output (no API call)...")
        return analyze_transcript_to_result(transcript, source, provenance, raw_output)

    log(f"Transcript received. Calling {get_provider_name()} model {get_model_name(get_provider_name())}...")
    if not sys.stderr.isatty():
        return analyze_transcript_to_result(transcript, source, provenance)

    stop_event = threading.Event()
    spinner_thread = threading.Thread(
        target=_spinner,
        args=(stop_event, "Analysis in progress"),
        daemon=True,
    )
    spinner_thread.start()
    try:
        return analyze_transcript_to_result(transcript, source, provenance)
    finally:
        stop_event.set()
        spinner_thread.join()


def analyze_safely(transcript, source, provenance, raw_output=None) -> dict[str, object]:
    """Never raises: provider errors become an analysis_failed result."""
    try:
        return run_analysis_with_progress(transcript, source, provenance, raw_output)
    except UsageError:
        raise
    except Exception as error:
        attempts = getattr(error, "wtp_attempts", 1)
        result = build_failure_result(source, provenance,
                                      f"Analysis failed after {attempts} attempt(s): {type(error).__name__}: {error}",
                                      error=error)
        log(f"Analysis failed after {attempts} attempt(s): {short_error(error)}\nNext: {result['next_step']}")
        result["run"] = {"provider": get_provider_name(), "model": get_model_name(get_provider_name()),
                         "attempts": {**(source.pop("_attempts", None) or {}), "model": attempts}}
        return result


def process_youtube_source(
    url: str,
    provenance: dict[str, str | None],
    source_id: str | None = None,
) -> tuple[dict[str, object], str | None]:
    """Returns (result, transcript). transcript is None when fetching failed."""
    normalized_url = normalize_youtube_input(url)

    try:
        video_id = extract_video_id(normalized_url)
    except ValueError as error:
        source = build_source_record(
            source_id=source_id or build_source_id("youtube_url"),
            url=normalized_url,
            video_id=None,
            input_type="youtube_url",
            transcript_status="failed",
        )
        result = build_failure_result(source, provenance, f"Transcript fetch failed: {error}",
                                      status="transcript_failed", error=error)
        log(f"Transcript fetch failed: {short_error(error)}\nNext: {result['next_step']}")
        return result, None

    source = build_source_record(
        source_id=source_id or build_source_id("youtube_url", video_id),
        url=normalized_url,
        video_id=video_id,
        input_type="youtube_url",
        transcript_status="fetched",
    )

    log(f"Fetching transcript for {video_id}...")
    try:
        transcript, fetch_attempts = fetch_transcript(normalized_url)
    except Exception as error:
        attempts = getattr(error, "wtp_attempts", 1)
        source["transcript_status"] = "failed"
        result = build_failure_result(
            source, provenance,
            f"Transcript fetch failed after {attempts} attempt(s): {type(error).__name__}: {error}",
            status="transcript_failed", error=error)
        log(f"Transcript fetch failed after {attempts} attempt(s): {short_error(error)}\n"
            f"Next: {result['next_step']}")
        result["run"] = {"attempts": {"transcript": attempts}}
        return result, None
    source["_attempts"] = {"transcript": fetch_attempts}
    log(f"Transcript fetched ({len(transcript)} chars).")
    return analyze_safely(transcript, source, provenance), transcript


def process_pasted_transcript(
    transcript: str,
    provenance: dict[str, str | None],
    source_id: str | None = None,
    raw_output: str | None = None,
) -> tuple[dict[str, object], str | None]:
    source = build_source_record(
        source_id=source_id or build_source_id("pasted_transcript"),
        url=None,
        video_id=None,
        input_type="pasted_transcript",
        transcript_status="pasted",
    )
    if not transcript.strip():
        source["transcript_status"] = "failed"
        return build_failure_result(source, provenance, "Transcript is empty.",
                                    status="transcript_failed"), None
    log(f"Transcript captured ({len(transcript)} chars).")
    return analyze_safely(transcript, source, provenance, raw_output), transcript


def process_manifest_source(source_spec: dict[str, object]) -> tuple[dict[str, object], str | None]:
    provenance = normalize_provenance(source_spec.get("provenance"))
    source_id = str(source_spec.get("source_id")).strip() if source_spec.get("source_id") else None
    transcript = str(source_spec.get("transcript") or "").strip()
    url = str(source_spec.get("url") or "").strip()

    if transcript:
        return process_pasted_transcript(transcript, provenance, source_id=source_id)
    if url:
        return process_youtube_source(url, provenance, source_id=source_id)

    source = build_source_record(
        source_id=source_id or build_source_id("pasted_transcript"),
        url=None,
        video_id=None,
        input_type="pasted_transcript",
        transcript_status="failed",
    )
    return build_failure_result(source, provenance,
                                "Manifest source is missing both 'url' and 'transcript'.",
                                status="transcript_failed"), None


# ---------------------------------------------------------------- output

def save_source(result, transcript, output_dir=DEFAULT_OUTPUT_DIR, artifact_id=None) -> dict[str, str]:
    return write_artifacts(result, render_result(result), output_dir=output_dir,
                           session_id=artifact_id, transcript=transcript)


def emit(payload: dict[str, object], text_report: str, json_mode: bool, title: str) -> None:
    if json_mode:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(f"\n=== {title} ===\n")
    print(safe_console_text(text_report))
    artifacts = payload.get("artifacts") or {}
    print("\nArtifacts saved:" if title == "RESULTS" else "\nSession artifacts saved:")
    for label, key in (("Text", "text_path"), ("JSON", "json_path"), ("Transcript", "transcript_path")):
        if artifacts.get(key):
            print(f"- {label}: {artifacts[key]}")


def run_sources(
    jobs: list,
    *,
    session_id: str,
    output_dir: Path,
    json_mode: bool,
    session_context: dict[str, object] | None = None,
    manifest_path: str | None = None,
) -> int:
    """jobs: zero-arg callables returning (result, transcript). Writes every source
    and a session rollup; prints the session (JSON or report); returns worst exit."""
    results = []
    log(f"Session {session_id}: {len(jobs)} source(s). Output: {output_dir}")
    for index, job in enumerate(jobs, start=1):
        log(f"--- Source {index}/{len(jobs)} ---")
        result, transcript = job()
        paths = save_source(result, transcript, output_dir=str(output_dir),
                            artifact_id=str(result["source"]["source_id"]))
        log(f"Saved {result['source']['source_id']} [{result['status']}]: {paths['json_path']}")
        results.append(result)

    session_result = build_session_result(results, session_id=session_id,
                                          session_context=session_context,
                                          manifest_path=manifest_path)
    session_result["artifacts"] = {}
    text_report = render_session_report(session_result)
    write_session_artifacts(session_result, text_report, output_dir=output_dir, session_id=session_id)
    emit(session_result, text_report, json_mode, "SESSION RESULTS")
    return contract.worst_exit([contract.STATUS_EXIT[r["status"]] for r in results])


def run_single(result_and_transcript, json_mode: bool, output_dir: str) -> int:
    result, transcript = result_and_transcript
    text_report = render_result(result)
    # Name files after the source (e.g. youtube_url-<video>-<time>), like batch runs do.
    write_artifacts(result, text_report, output_dir=output_dir, transcript=transcript,
                    session_id=str(result["source"]["source_id"]))
    emit(result, text_report, json_mode, "RESULTS")
    return contract.STATUS_EXIT[result["status"]]


def run_interactive_mode(output_dir: str) -> int:
    log("\n=== WTP Signal Extractor ===\n")
    log("Choose input method:\n1 - Youtube URL\n2 - Paste transcript text directly")
    choice = input("\nEnter 1 or 2: ").strip()
    provenance = default_provenance()

    if choice == "1":
        url = normalize_youtube_input(input("Enter Youtube URL: "))
        return run_single(process_youtube_source(url, provenance), False, output_dir)

    if choice == "2":
        log("Paste transcript. Type End on its own line to finish.")
        lines = []
        while True:
            line = input()
            if line.strip() == "End":
                break
            lines.append(line)
        transcript = "\n".join(lines)
        if not transcript.strip():
            log("Transcript is empty")
            return contract.EXIT_SOURCE_FAILED
        return run_single(process_pasted_transcript(transcript, provenance), False, output_dir)

    log("Invalid choice")
    return contract.EXIT_USAGE


# ---------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract WTP and FGP signals from transcripts with an LLM, verify every quote "
                    "against the transcript, and write text + JSON artifacts.",
        epilog="Agents: run `python main.py --describe` for the full machine contract "
               "(exit codes, output schema, vocabularies, domain terms). "
               "Exit codes: " + "; ".join(f"{k}={v.split(':')[0]}" for k, v in contract.EXIT_CODES.items()),
    )
    source = parser.add_argument_group("input (pick one; none = interactive, TTY only)")
    source.add_argument("--url", help="One YouTube URL.")
    source.add_argument("--transcript-file", metavar="PATH",
                        help="A transcript text file, or '-' to read stdin.")
    source.add_argument("--urls", nargs="+", help="Several YouTube URLs, run as one session.")
    source.add_argument("--urls-file", metavar="PATH", help="Text file, one YouTube URL per line (# comments ok).")
    source.add_argument("--session", metavar="PATH",
                        help="JSON session manifest (see `--describe` manifest_example).")
    parser.add_argument("--replay", metavar="RAW_PATH",
                        help="Re-parse a saved model output instead of calling the model. Combine with "
                             "--transcript-file so quotes and heuristics can be checked. No network.")
    parser.add_argument("--json", action="store_true",
                        help="Print one JSON document (result or session) on stdout; logs go to stderr.")
    parser.add_argument("--out-dir", metavar="DIR",
                        help=f"Where artifacts go (default {DEFAULT_OUTPUT_DIR}/, or "
                             f"{DEFAULT_REPORTS_DIR}/<session_id>/ for --session).")
    parser.add_argument("--describe", action="store_true",
                        help="Print the machine contract as JSON and exit. No network.")
    parser.add_argument("--version", action="store_true", help="Print the version and exit.")
    parser.add_argument("--check-update", action="store_true",
                        help="Compare with the latest GitHub release (network). JSON; exit 0 = current, "
                             "1 = update available, 3 = GitHub unreachable.")
    parser.add_argument("--self-update", action="store_true",
                        help="Install the latest GitHub release over this one (uv tool installs only). JSON.")
    parser.add_argument("--check", action="store_true",
                        help="Preflight: provider, model, API key present, dirs writable. JSON, no network.")
    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def cli_flags() -> list[dict[str, object]]:
    flags = []
    for action in build_parser()._actions:
        if not action.option_strings or action.dest == "help":
            continue
        flags.append({"flag": action.option_strings[-1], "help": action.help,
                      "takes_value": action.nargs != 0,
                      "repeatable": action.nargs == "+"})
    return flags


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or [])

    if args.version:
        print(contract.TOOL_VERSION)
        return contract.EXIT_OK
    if args.check_update or args.self_update:
        try:
            info = install.self_update() if args.self_update else install.check_update()
        except OSError as error:
            log(f"error: could not reach GitHub: {error}")
            return contract.EXIT_SOURCE_FAILED
        print(json.dumps(info, indent=2))
        if args.self_update:
            return contract.EXIT_OK if info["updated"] or not info["update_available"] else contract.EXIT_USAGE
        return contract.EXIT_DEGRADED if info["update_available"] else contract.EXIT_OK
    if args.describe:
        print(json.dumps(contract.describe(cli_flags()), indent=2, ensure_ascii=False))
        return contract.EXIT_OK
    if args.check:
        checks = preflight()
        print(json.dumps(checks, indent=2))
        return contract.EXIT_OK if checks["ok"] else contract.EXIT_USAGE

    inputs = [name for name in ("url", "transcript_file", "urls", "urls_file", "session")
              if getattr(args, name)]
    try:
        if len(inputs) > 1:
            raise UsageError(f"Pick one input, got: {', '.join('--' + i.replace('_', '-') for i in inputs)}")
        if args.replay and inputs and inputs[0] != "transcript_file":
            raise UsageError("--replay works with --transcript-file (or alone), not with URLs or sessions.")

        output_dir = args.out_dir or DEFAULT_OUTPUT_DIR

        if args.replay:
            raw = read_text_input(args.replay)
            transcript = read_text_input(args.transcript_file) if args.transcript_file else ""
            if not transcript:
                log("No --transcript-file: quotes will not be verified and heuristics see no text.")
            source = build_source_record(source_id=build_source_id("replay"), url=None, video_id=None,
                                         input_type="pasted_transcript", transcript_status="pasted")
            result = analyze_safely(transcript, source, default_provenance(), raw_output=raw)
            return run_single((result, transcript or None), args.json, output_dir)

        if args.url:
            return run_single(process_youtube_source(args.url, default_provenance()), args.json, output_dir)

        if args.transcript_file:
            transcript = read_text_input(args.transcript_file)
            return run_single(process_pasted_transcript(transcript, default_provenance()), args.json, output_dir)

        if args.session:
            manifest = load_session_manifest(args.session)
            session_id = str(manifest.get("session_id") or build_session_id())
            jobs = [
                (lambda spec=spec: process_manifest_source(spec if isinstance(spec, dict) else {}))
                for spec in manifest["sources"]
            ]
            return run_sources(
                jobs,
                session_id=session_id,
                output_dir=Path(args.out_dir) if args.out_dir else build_reports_output_dir(session_id),
                json_mode=args.json,
                session_context=normalize_session_context(manifest.get("session_context")),
                manifest_path=str(Path(args.session)),
            )

        if args.urls or args.urls_file:
            urls = collect_batch_urls(args)
            if not urls:
                raise UsageError("No URLs found for batch processing.")
            jobs = [(lambda u=u: process_youtube_source(u, default_provenance())) for u in urls]
            return run_sources(jobs, session_id=build_session_id(), output_dir=Path(output_dir),
                               json_mode=args.json)

        if not sys.stdin.isatty():
            raise UsageError("No input given and stdin is not a terminal. Use --url, --transcript-file, "
                             "--urls, --urls-file or --session (see --help / --describe).")
        return run_interactive_mode(output_dir)
    except UsageError as error:
        log(f"error: {error}")
        return contract.EXIT_USAGE


def entrypoint() -> None:
    """The `wtp` command."""
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    entrypoint()
