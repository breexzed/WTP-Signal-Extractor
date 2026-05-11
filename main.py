from __future__ import annotations

import os
import re
import sys
import threading
import time
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from google import genai
from google.genai import types
from youtube_transcript_api import YouTubeTranscriptApi

from diagnostics import build_diagnostics
from extract import parse_model_output
from prompt import SYSTEM_PROMPT
from render import render_result, safe_console_text
from schemas import merge_result
from session_store import write_artifacts

MODEL_NAME = "gemini-2.5-flash"

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


def get_client() -> genai.Client:
    return genai.Client(api_key=get_api_key())


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


def build_source_id(input_type: str, video_id: str | None = None) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if video_id:
        return f"{input_type}-{video_id}-{timestamp}"
    return f"{input_type}-{timestamp}"


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
    client = get_client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    )
    return response.text or ""


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
    show_status("\nTranscript received. Routing analysis request to Gemini...")
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


def persist_and_print(result: dict[str, object]) -> None:
    text_report = render_result(result)
    saved_paths = write_artifacts(result, text_report)
    print("\n=== RESULTS ===\n")
    print(safe_console_text(text_report))
    print("\nArtifacts saved:")
    print(f"- Text: {saved_paths['text_path']}")
    print(f"- JSON: {saved_paths['json_path']}")


def main() -> None:
    print("\n=== WTP Signal Extractor ===\n")
    print("Choose input method:")
    print("1 - Youtube URL")
    print("2 - Paste transcript text directly")

    choice = input("\nEnter 1 or 2: ").strip()
    provenance = default_provenance()

    if choice == "1":
        url = normalize_youtube_input(input("Enter Youtube URL: "))
        video_id = None
        try:
            video_id = extract_video_id(url)
        except ValueError:
            pass
        source = build_source_record(
            source_id=build_source_id("youtube_url", video_id),
            url=url,
            video_id=video_id,
            input_type="youtube_url",
            transcript_status="fetched",
        )

        show_status("\nFetching transcript...")
        try:
            transcript = get_transcript_from_url(url)
            show_status(f"Transcript fetched successfully ({len(transcript)} chars).")
        except Exception as error:
            print(f"Error fetching transcript: {error}")
            source["transcript_status"] = "failed"
            failure_result = build_failure_result(
                source,
                provenance,
                f"Transcript fetch failed: {error}",
            )
            persist_and_print(failure_result)
            return

    elif choice == "2":
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

        source = build_source_record(
            source_id=build_source_id("pasted_transcript"),
            url=None,
            video_id=None,
            input_type="pasted_transcript",
            transcript_status="pasted",
        )
        show_status(f"Transcript captured successfully ({len(transcript)} chars).")

    else:
        print("Invalid choice")
        return

    try:
        result = run_analysis_with_progress(transcript, source, provenance)
        persist_and_print(result)
    except Exception as error:
        print(f"Analysis error: {error}")
        failure_result = build_failure_result(
            source,
            provenance,
            f"Analysis failed: {error}",
        )
        persist_and_print(failure_result)


if __name__ == "__main__":
    main()
