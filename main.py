from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi

from aggregate import build_session_result
from diagnostics import build_diagnostics
from extract import parse_model_output
from prompt import SYSTEM_PROMPT
from providers.base import ProviderConfig
from providers.gemini import GeminiProvider
from providers.openai_compatible import OpenAICompatibleProvider
from render import render_result, render_session_report, safe_console_text
from schemas import merge_result
from session_store import sanitize_token, write_artifacts, write_session_artifacts

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_OUTPUT_DIR = "outputs"
DEFAULT_REPORTS_DIR = "reports"
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

load_dotenv()


def show_status(message: str) -> None:
    print(message, flush=True)


def normalize_youtube_input(text: str) -> str:
    text = text.strip()
    match = re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s)>,]+", text)
    if match:
        return match.group(0).rstrip(".,]")
    return text


def get_api_key() -> str:
    for env_var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEYS"):
        value = os.getenv(env_var)
        if value:
            return value

    raise RuntimeError(
        "Missing Gemini API key. Set GEMINI_API_KEY or GOOGLE_API_KEY in your .env file."
    )


def get_provider_name() -> str:
    return os.getenv("LLM_PROVIDER", "gemini").strip().lower()


def get_model_name(provider_name: str) -> str:
    if provider_name == "openai_compatible":
        return (
            os.getenv("OPENAI_COMPATIBLE_MODEL_NAME")
            or os.getenv("LLM_MODEL_NAME")
            or "gpt-4.1-mini"
        )
    return os.getenv("GEMINI_MODEL_NAME") or os.getenv("LLM_MODEL_NAME") or DEFAULT_GEMINI_MODEL


def get_openai_compatible_api_key() -> str:
    value = os.getenv("OPENAI_COMPATIBLE_API_KEY") or os.getenv("LLM_API_KEY")
    if value:
        return value
    raise RuntimeError(
        "Missing OpenAI-compatible API key. Set OPENAI_COMPATIBLE_API_KEY or LLM_API_KEY."
    )


def get_openai_compatible_base_url() -> str:
    value = os.getenv("OPENAI_COMPATIBLE_BASE_URL") or os.getenv("LLM_BASE_URL")
    if value:
        return value
    raise RuntimeError(
        "Missing OpenAI-compatible base URL. Set OPENAI_COMPATIBLE_BASE_URL or LLM_BASE_URL."
    )


def get_provider_config() -> ProviderConfig:
    provider_name = get_provider_name()
    if provider_name == "openai_compatible":
        return ProviderConfig(
            provider_name=provider_name,
            model_name=get_model_name(provider_name),
            api_key=get_openai_compatible_api_key(),
            base_url=get_openai_compatible_base_url(),
        )
    if provider_name != "gemini":
        raise RuntimeError(
            f"Unsupported provider '{provider_name}'. Supported providers: gemini, openai_compatible."
        )
    return ProviderConfig(
        provider_name=provider_name,
        model_name=get_model_name(provider_name),
        api_key=get_api_key(),
    )


def get_llm_provider():
    config = get_provider_config()
    if config.provider_name == "openai_compatible":
        return OpenAICompatibleProvider(config)
    return GeminiProvider(config)


def get_display_provider_name() -> str:
    provider_name = get_provider_name()
    if provider_name == "openai_compatible":
        return "the configured OpenAI-compatible model"
    return "Gemini"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract WTP and FGP signals from one or more transcript sources.",
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        help="One or more YouTube URLs to process in batch.",
    )
    parser.add_argument(
        "--urls-file",
        help="Path to a text file containing one YouTube URL per line.",
    )
    parser.add_argument(
        "--session",
        help="Path to a JSON session manifest containing one or more sources.",
    )
    return parser.parse_args(argv)


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

    raise ValueError("Invalid Youtube Url")


def get_transcript_from_url(url: str) -> str:
    video_id = extract_video_id(url)
    transcript_data = YouTubeTranscriptApi().fetch(video_id)
    return " ".join(
        entry.text if hasattr(entry, "text") else entry["text"]
        for entry in transcript_data
    )


def load_urls_from_file(path: str) -> list[str]:
    file_path = Path(path)
    if not file_path.exists():
        raise RuntimeError(f"URLs file not found: {file_path}")

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


def build_source_id(input_type: str, video_id: str | None = None) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
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
        raw_value = None if value is None else value.get(key)
        provenance[key] = normalize_optional_string(raw_value)
    return provenance


def normalize_session_context(value: dict[str, object] | None) -> dict[str, str | None]:
    session_context = default_session_context()
    for field in session_context:
        raw_value = None if value is None else value.get(field)
        session_context[field] = normalize_optional_string(raw_value)
    return session_context


def load_session_manifest(path: str) -> dict[str, object]:
    file_path = Path(path)
    if not file_path.exists():
        raise RuntimeError(f"Session manifest not found: {file_path}")

    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Session manifest is not valid JSON: {error}") from error

    if not isinstance(payload, dict):
        raise RuntimeError("Session manifest must be a JSON object.")

    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise RuntimeError("Session manifest must include a 'sources' list.")

    return payload


def build_reports_output_dir(session_id: str) -> Path:
    return Path(DEFAULT_REPORTS_DIR) / sanitize_token(session_id, fallback="session")


def _spinner(stop_event: threading.Event, label: str) -> None:
    frames = "|/-\\"
    index = 0
    while not stop_event.is_set():
        frame = frames[index % len(frames)]
        sys.stdout.write(f"\r{label} {frame}")
        sys.stdout.flush()
        index += 1
        time.sleep(0.12)
    sys.stdout.write(f"\r{label} done\n")
    sys.stdout.flush()


def call_model(transcript: str) -> str:
    prompt = f"Analyze this transcript for market intelligence signals:\n\n{transcript}"
    provider = get_llm_provider()
    return provider.generate(prompt, SYSTEM_PROMPT)


def analyze_transcript_to_result(
    transcript: str,
    source: dict[str, str | None],
    provenance: dict[str, str | None],
) -> dict[str, object]:
    raw_output = call_model(transcript)
    parsed = parse_model_output(raw_output)
    diagnostics = build_diagnostics(parsed, transcript, provenance)
    source["source_type"] = diagnostics.pop("source_type")
    source["speaker_type"] = diagnostics.pop("speaker_type")

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


def build_failure_result(
    source: dict[str, str | None],
    provenance: dict[str, str | None],
    warning: str,
) -> dict[str, object]:
    return merge_result(
        source=source,
        provenance=provenance,
        pass1={},
        pass2={},
        diagnostics={},
        combined_summary={},
        parse_warnings=[warning],
        raw_output=None,
    )


def run_analysis_with_progress(
    transcript: str,
    source: dict[str, str | None],
    provenance: dict[str, str | None],
) -> dict[str, object]:
    show_status(
        f"\nTranscript received. Routing analysis request to {get_display_provider_name()}..."
    )
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


def save_source_artifacts(
    result: dict[str, object],
    *,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    artifact_id: str | None = None,
) -> dict[str, str]:
    text_report = render_result(result)
    return write_artifacts(result, text_report, output_dir=output_dir, session_id=artifact_id)


def save_session_artifacts(
    session_result: dict[str, object],
    *,
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> dict[str, str]:
    text_report = render_session_report(session_result)
    return write_session_artifacts(
        session_result,
        text_report,
        output_dir=output_dir,
        session_id=str(session_result["session_id"]),
    )


def persist_and_print(result: dict[str, object]) -> None:
    text_report = render_result(result)
    saved_paths = write_artifacts(result, text_report)
    print("\n=== RESULTS ===\n")
    print(safe_console_text(text_report))
    print("\nArtifacts saved:")
    print(f"- Text: {saved_paths['text_path']}")
    print(f"- JSON: {saved_paths['json_path']}")


def persist_session_and_print(session_result: dict[str, object]) -> None:
    text_report = render_session_report(session_result)
    saved_paths = write_session_artifacts(
        session_result,
        text_report,
        session_id=str(session_result["session_id"]),
    )
    print("\n=== SESSION RESULTS ===\n")
    print(safe_console_text(text_report))
    print("\nSession artifacts saved:")
    print(f"- Text: {saved_paths['text_path']}")
    print(f"- JSON: {saved_paths['json_path']}")


def process_youtube_source(
    url: str,
    provenance: dict[str, str | None],
    source_id: str | None = None,
) -> dict[str, object]:
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
        print(f"Error fetching transcript: {error}")
        return build_failure_result(
            source,
            provenance,
            f"Transcript fetch failed: {error}",
        )

    source = build_source_record(
        source_id=source_id or build_source_id("youtube_url", video_id),
        url=normalized_url,
        video_id=video_id,
        input_type="youtube_url",
        transcript_status="fetched",
    )

    show_status("\nFetching transcript...")
    try:
        transcript = get_transcript_from_url(normalized_url)
        show_status(f"Transcript fetched successfully ({len(transcript)} chars).")
    except Exception as error:
        print(f"Error fetching transcript: {error}")
        source["transcript_status"] = "failed"
        return build_failure_result(
            source,
            provenance,
            f"Transcript fetch failed: {error}",
        )

    try:
        return run_analysis_with_progress(transcript, source, provenance)
    except Exception as error:
        print(f"Analysis error: {error}")
        return build_failure_result(
            source,
            provenance,
            f"Analysis failed: {error}",
        )


def process_pasted_transcript(
    transcript: str,
    provenance: dict[str, str | None],
    source_id: str | None = None,
) -> dict[str, object]:
    source = build_source_record(
        source_id=source_id or build_source_id("pasted_transcript"),
        url=None,
        video_id=None,
        input_type="pasted_transcript",
        transcript_status="pasted",
    )
    show_status(f"Transcript captured successfully ({len(transcript)} chars).")

    try:
        return run_analysis_with_progress(transcript, source, provenance)
    except Exception as error:
        print(f"Analysis error: {error}")
        return build_failure_result(
            source,
            provenance,
            f"Analysis failed: {error}",
        )


def run_batch_mode(urls: list[str]) -> None:
    session_id = build_session_id()
    results = []

    print("\n=== WTP Batch Session ===\n")
    print(f"Session ID: {session_id}")
    print(f"Source count: {len(urls)}")

    for index, url in enumerate(urls, start=1):
        show_status(f"\n--- Source {index}/{len(urls)} ---")
        result = process_youtube_source(url, default_provenance())
        results.append(result)
        saved_paths = save_source_artifacts(
            result,
            artifact_id=str(result["source"]["source_id"]),
        )
        show_status(
            f"Saved source artifacts for {result['source']['source_id']}:"
            f" {saved_paths['text_path']} | {saved_paths['json_path']}"
        )

    session_result = build_session_result(results, session_id=session_id)
    persist_session_and_print(session_result)


def process_manifest_source(source_spec: dict[str, object]) -> dict[str, object]:
    provenance = normalize_provenance(source_spec.get("provenance"))
    source_id = str(source_spec.get("source_id")).strip() if source_spec.get("source_id") else None
    transcript = str(source_spec.get("transcript") or "").strip()
    url = str(source_spec.get("url") or "").strip()

    if transcript:
        return process_pasted_transcript(transcript, provenance, source_id=source_id)
    if url:
        return process_youtube_source(url, provenance, source_id=source_id)

    fallback_source_id = source_id or build_source_id("pasted_transcript")
    source = build_source_record(
        source_id=fallback_source_id,
        url=None,
        video_id=None,
        input_type="pasted_transcript",
        transcript_status="failed",
    )
    return build_failure_result(
        source,
        provenance,
        "Manifest source is missing both 'url' and 'transcript'.",
    )


def run_session_manifest_mode(manifest_path: str) -> None:
    manifest = load_session_manifest(manifest_path)
    session_id = str(manifest.get("session_id") or build_session_id())
    session_context = normalize_session_context(manifest.get("session_context"))
    reports_dir = build_reports_output_dir(session_id)
    sources = manifest["sources"]
    results = []

    print("\n=== WTP Session Manifest Run ===\n")
    print(f"Session ID: {session_id}")
    print(f"Source count: {len(sources)}")
    print(f"Reports directory: {reports_dir}")

    for index, source_spec in enumerate(sources, start=1):
        if not isinstance(source_spec, dict):
            source_spec = {}
        show_status(f"\n--- Source {index}/{len(sources)} ---")
        result = process_manifest_source(source_spec)
        results.append(result)
        saved_paths = save_source_artifacts(
            result,
            output_dir=str(reports_dir),
            artifact_id=str(result["source"]["source_id"]),
        )
        show_status(
            f"Saved source artifacts for {result['source']['source_id']}:"
            f" {saved_paths['text_path']} | {saved_paths['json_path']}"
        )

    session_result = build_session_result(
        results,
        session_id=session_id,
        session_context=session_context,
        manifest_path=str(Path(manifest_path)),
    )
    text_report = render_session_report(session_result)
    saved_paths = write_session_artifacts(
        session_result,
        text_report,
        output_dir=reports_dir,
        session_id=session_id,
    )
    print("\n=== SESSION RESULTS ===\n")
    print(safe_console_text(text_report))
    print("\nSession artifacts saved:")
    print(f"- Text: {saved_paths['text_path']}")
    print(f"- JSON: {saved_paths['json_path']}")


def run_interactive_mode() -> None:
    print("\n=== WTP Signal Extractor ===\n")
    print("Choose input method:")
    print("1 - Youtube URL")
    print("2 - Paste transcript text directly")

    choice = input("\nEnter 1 or 2: ").strip()
    provenance = default_provenance()

    if choice == "1":
        url = normalize_youtube_input(input("Enter Youtube URL: "))
        result = process_youtube_source(url, provenance)
        persist_and_print(result)
        return

    if choice == "2":
        print("Paste transcript. Type End to finish, hit ENTER")
        lines = []

        while True:
            line = input()
            if line.strip() == "End":
                break
            lines.append(line)

        transcript = "\n".join(lines)

        if not transcript.strip():
            print("Transcript is empty")
            return

        result = process_pasted_transcript(transcript, provenance)
        persist_and_print(result)
        return

    print("Invalid choice")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv or [])
    if args.session:
        try:
            run_session_manifest_mode(args.session)
        except RuntimeError as error:
            print(error)
        return

    try:
        batch_urls = collect_batch_urls(args)
    except RuntimeError as error:
        print(error)
        return

    if args.urls or args.urls_file:
        if not batch_urls:
            print("No URLs found for batch processing.")
            return
        run_batch_mode(batch_urls)
        return

    run_interactive_mode()


if __name__ == "__main__":
    main(sys.argv[1:])
