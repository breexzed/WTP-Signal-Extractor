import os
import re
import sys
import threading
import time
from collections import Counter
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from google import genai
from google.genai import types
from youtube_transcript_api import YouTubeTranscriptApi

from prompt import SYSTEM_PROMPT

MODEL_NAME = "gemini-2.5-flash"

SECTION_PATTERNS = [
    ("behavior", r"BEHAVIOR[- ]LEVEL SIGNALS"),
    ("opinion", r"OPINION[- ]LEVEL SIGNALS"),
    ("pass1_summary", r"PASS 1 SUMMARY"),
    ("pass2_title", r"PASS 2:\s*FGP PIPELINE INTELLIGENCE"),
    ("category_a", r"CATEGORY A\s*[—-]\s*CASCADE INDICATORS"),
    ("category_b", r"CATEGORY B\s*[—-]\s*GATEKEEPER MENTIONS"),
    ("category_c", r"CATEGORY C\s*[—-]\s*POSITION INTELLIGENCE"),
    ("category_d", r"CATEGORY D\s*[—-]\s*SUBNICHE CULTURE SIGNALS"),
    ("pass2_summary", r"PASS 2 SUMMARY"),
    ("combined_summary", r"COMBINED INTELLIGENCE SUMMARY"),
    ("top3", r"TOP 3 ACTIONABLE SIGNALS ACROSS BOTH PASSES:?"),
    ("hypothesis", r"ONE HYPOTHESIS WORTH TESTING:?"),
]

PASS1_SUMMARY_FIELDS = {
    "TOTAL HIGH-SIGNAL MOMENTS": "total_high_signal",
    "DOMINANT PAIN CATEGORY": "dominant_pain_category",
    "CONFIDENCE LEVEL": "confidence_level",
}

PASS2_SUMMARY_FIELDS = {
    "STRONGEST CASCADE FOUND": "strongest_cascade",
    "HIGHEST-SIGNAL GATEKEEPER MENTION": "highest_signal_gatekeeper",
    "POSITION INTELLIGENCE CONFIDENCE": "position_intelligence_confidence",
    "RECOMMENDED NEXT ACTION": "recommended_next_action",
}

load_dotenv()


def show_status(message: str) -> None:
    print(message, flush=True)


def safe_console_text(text: str) -> str:
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2192": "->",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u00a0": " ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)

    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding)


def clean_model_output(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[*`_]+", "", text)
    return text


def is_decorative_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return all(character in "═=-_~#·.?" for character in stripped)


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


def get_section_bounds(text: str) -> dict[str, tuple[int, int]]:
    found_sections = []
    for key, pattern in SECTION_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            found_sections.append((match.start(), match.end(), key))

    found_sections.sort()
    bounds: dict[str, tuple[int, int]] = {}
    for index, (start, end, key) in enumerate(found_sections):
        next_start = found_sections[index + 1][0] if index + 1 < len(found_sections) else len(text)
        bounds[key] = (end, next_start)
    return bounds


def extract_section_text(text: str, bounds: dict[str, tuple[int, int]], key: str) -> str:
    if key not in bounds:
        return ""
    start, end = bounds[key]
    return text[start:end].strip()


def parse_labeled_blocks(section_text: str, expected_fields: list[str]) -> list[dict[str, str]]:
    expected = {field.upper(): field for field in expected_fields}
    blocks: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    active_field: str | None = None

    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line or line == "---" or line.lower() == "none found." or is_decorative_line(line):
            continue

        line = re.sub(r"^[\-\d\.\)\s]+", "", line)
        match = re.match(r"([A-Z][A-Z0-9 /\-]+):\s*(.*)$", line)

        if match:
            label = match.group(1).strip().upper()
            value = match.group(2).strip()
            if label in expected:
                canonical = expected[label]
                if canonical == "QUOTE":
                    if current:
                        blocks.append(current)
                    current = {}
                if current is None:
                    current = {}
                current[canonical] = value
                active_field = canonical
                continue

        if current is not None and active_field:
            current[active_field] = f"{current[active_field]} {line}".strip()

    if current:
        blocks.append(current)

    return blocks


def parse_key_value_lines(section_text: str, field_map: dict[str, str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    active_key: str | None = None

    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line or line == "---" or is_decorative_line(line):
            continue

        line = re.sub(r"^[\-\d\.\)\s]+", "", line)
        match = re.match(r"([A-Z][A-Z0-9 /\-]+):\s*(.*)$", line, flags=re.IGNORECASE)
        if match:
            label = match.group(1).strip().upper()
            value = match.group(2).strip()
            if label in field_map:
                active_key = field_map[label]
                parsed[active_key] = value
                continue

        if active_key:
            parsed[active_key] = f"{parsed[active_key]} {line}".strip()

    return parsed


def parse_numbered_items(section_text: str) -> list[str]:
    items: list[str] = []
    current: str | None = None

    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line or line == "---" or is_decorative_line(line):
            continue

        match = re.match(r"(\d+)\.\s*(.*)$", line)
        if match:
            if current is not None:
                items.append(current.strip())
            current = match.group(2).strip()
            continue

        if current is not None:
            current = f"{current} {line}".strip()

    if current is not None:
        items.append(current.strip())

    return items


def extract_freeform_text(section_text: str) -> str:
    lines = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line or line == "---" or is_decorative_line(line):
            continue
        line = re.sub(r"^[\-\d\.\)\s]+", "", line)
        lines.append(line)
    return " ".join(lines).strip()


def most_common_behavior_category(signals: list[dict[str, str]]) -> str:
    categories = [signal.get("CATEGORY", "").strip() for signal in signals if signal.get("CATEGORY")]
    if not categories:
        return "None found."
    return Counter(categories).most_common(1)[0][0]


def cascade_depth_rank(depth: str) -> int:
    normalized = depth.strip().lower()
    if "three-layer" in normalized:
        return 3
    if "two-layer" in normalized:
        return 2
    if "single-layer" in normalized:
        return 1
    return 0


def strongest_cascade(signals: list[dict[str, str]]) -> str:
    if not signals:
        return "None found."
    signal = max(signals, key=lambda item: cascade_depth_rank(item.get("CASCADE DEPTH", "")))
    quote = signal.get("QUOTE", "Not provided.")
    depth = signal.get("CASCADE DEPTH", "Not provided.")
    return f"{quote} ({depth})"


def highest_signal_gatekeeper(signals: list[dict[str, str]]) -> str:
    if not signals:
        return "None found."
    signal = signals[0]
    entity = signal.get("ENTITY NAMED", "Not provided.")
    dependency_type = signal.get("DEPENDENCY TYPE", "Not provided.")
    return f"{entity} ({dependency_type})"


def infer_position_intelligence_confidence(signals: list[dict[str, str]]) -> str:
    if not signals:
        return "Low"

    normalized = [signal.get("CONFIDENCE", "").strip().lower() for signal in signals]
    if normalized and all(value == "high" for value in normalized if value):
        return "High"
    if any(value in {"high", "medium"} for value in normalized):
        return "Medium"
    return "Low"


def render_signal_blocks(signals: list[dict[str, str]], fields: list[tuple[str, str]]) -> str:
    if not signals:
        return "None found."

    rendered_blocks = []
    for signal in signals:
        lines = []
        for field_name, fallback in fields:
            value = signal.get(field_name, "").strip() or fallback
            lines.append(f"- {field_name}: {value}")
        rendered_blocks.append("\n".join(lines))
    return "\n\n".join(rendered_blocks)


def render_numbered_items(items: list[str], target_count: int = 3) -> str:
    normalized = list(items[:target_count])
    while len(normalized) < target_count:
        normalized.append("None found.")
    return "\n".join(f"{index}. {item}" for index, item in enumerate(normalized, start=1))


def format_analysis_output(raw_output: str) -> str:
    text = clean_model_output(raw_output)
    bounds = get_section_bounds(text)

    behavior_signals = parse_labeled_blocks(
        extract_section_text(text, bounds, "behavior"),
        ["QUOTE", "CATEGORY", "WTP IMPLICATION"],
    )
    opinion_signals = parse_labeled_blocks(
        extract_section_text(text, bounds, "opinion"),
        ["QUOTE", "WHY LOW SIGNAL"],
    )
    pass1_summary = parse_key_value_lines(
        extract_section_text(text, bounds, "pass1_summary"),
        PASS1_SUMMARY_FIELDS,
    )

    cascade_signals = parse_labeled_blocks(
        extract_section_text(text, bounds, "category_a"),
        ["QUOTE", "LAYERS BROKEN", "CASCADE DEPTH", "BUILD SIGNAL"],
    )
    gatekeeper_signals = parse_labeled_blocks(
        extract_section_text(text, bounds, "category_b"),
        [
            "QUOTE",
            "ENTITY NAMED",
            "DEPENDENCY TYPE",
            "OPERATOR RELATIONSHIP",
            "GATEKEEPER SIGNAL",
        ],
    )
    position_signals = parse_labeled_blocks(
        extract_section_text(text, bounds, "category_c"),
        ["QUOTE", "ENTITY", "WHAT THEY PROTECT", "CONFIDENCE"],
    )
    culture_signals = parse_labeled_blocks(
        extract_section_text(text, bounds, "category_d"),
        ["QUOTE", "SUBNICHE IDENTIFIED", "DIFFERENTIATION CLAIM", "FGP USE"],
    )
    pass2_summary = parse_key_value_lines(
        extract_section_text(text, bounds, "pass2_summary"),
        PASS2_SUMMARY_FIELDS,
    )

    top_three_signals = parse_numbered_items(extract_section_text(text, bounds, "top3"))
    hypothesis = extract_freeform_text(extract_section_text(text, bounds, "hypothesis")) or "None found."

    total_high_signal = pass1_summary.get("total_high_signal") or str(len(behavior_signals))
    dominant_pain_category = (
        pass1_summary.get("dominant_pain_category") or most_common_behavior_category(behavior_signals)
    )
    confidence_level = pass1_summary.get("confidence_level") or "Not provided."

    strongest_cascade_value = pass2_summary.get("strongest_cascade") or strongest_cascade(cascade_signals)
    highest_gatekeeper_value = (
        pass2_summary.get("highest_signal_gatekeeper") or highest_signal_gatekeeper(gatekeeper_signals)
    )
    position_confidence_value = (
        pass2_summary.get("position_intelligence_confidence")
        or infer_position_intelligence_confidence(position_signals)
    )
    recommended_next_action = pass2_summary.get("recommended_next_action") or "Not provided."

    behavior_block = render_signal_blocks(
        behavior_signals,
        [
            ("QUOTE", "Not provided."),
            ("CATEGORY", "Not provided."),
            ("WTP IMPLICATION", "Not provided."),
        ],
    )
    opinion_block = render_signal_blocks(
        opinion_signals,
        [
            ("QUOTE", "Not provided."),
            ("WHY LOW SIGNAL", "Not provided."),
        ],
    )
    cascade_block = render_signal_blocks(
        cascade_signals,
        [
            ("QUOTE", "Not provided."),
            ("LAYERS BROKEN", "Not provided."),
            ("CASCADE DEPTH", "Not provided."),
            ("BUILD SIGNAL", "Not provided."),
        ],
    )
    gatekeeper_block = render_signal_blocks(
        gatekeeper_signals,
        [
            ("QUOTE", "Not provided."),
            ("ENTITY NAMED", "Not provided."),
            ("DEPENDENCY TYPE", "Not provided."),
            ("OPERATOR RELATIONSHIP", "Not provided."),
            ("GATEKEEPER SIGNAL", "Not provided."),
        ],
    )
    position_block = render_signal_blocks(
        position_signals,
        [
            ("QUOTE", "Not provided."),
            ("ENTITY", "Not provided."),
            ("WHAT THEY PROTECT", "Not provided."),
            ("CONFIDENCE", "Not provided."),
        ],
    )
    culture_block = render_signal_blocks(
        culture_signals,
        [
            ("QUOTE", "Not provided."),
            ("SUBNICHE IDENTIFIED", "Not provided."),
            ("DIFFERENTIATION CLAIM", "Not provided."),
            ("FGP USE", "Not provided."),
        ],
    )

    return (
        "PASS 1: WILLINGNESS-TO-PAY SIGNALS\n\n"
        "BEHAVIOR-LEVEL SIGNALS (High WTP Evidence)\n"
        f"{behavior_block}\n\n"
        "OPINION-LEVEL SIGNALS (Low WTP Evidence)\n"
        f"{opinion_block}\n\n"
        "PASS 1 SUMMARY\n"
        f"- Total high-signal moments: {total_high_signal}\n"
        f"- Dominant pain category: {dominant_pain_category}\n"
        f"- Confidence level: {confidence_level}\n\n"
        "PASS 2: FGP PIPELINE INTELLIGENCE\n\n"
        "CATEGORY A — CASCADE INDICATORS\n"
        f"{cascade_block}\n\n"
        "CATEGORY B — GATEKEEPER MENTIONS\n"
        f"{gatekeeper_block}\n\n"
        "CATEGORY C — POSITION INTELLIGENCE\n"
        f"{position_block}\n\n"
        "CATEGORY D — SUBNICHE CULTURE SIGNALS\n"
        f"{culture_block}\n\n"
        "PASS 2 SUMMARY\n"
        f"- Strongest cascade found: {strongest_cascade_value}\n"
        f"- Highest-signal gatekeeper mention: {highest_gatekeeper_value}\n"
        f"- Position intelligence confidence: {position_confidence_value}\n"
        f"- Recommended next action: {recommended_next_action}\n\n"
        "COMBINED INTELLIGENCE SUMMARY\n\n"
        "TOP 3 ACTIONABLE SIGNALS ACROSS BOTH PASSES:\n"
        f"{render_numbered_items(top_three_signals)}\n\n"
        "ONE HYPOTHESIS WORTH TESTING:\n"
        f"{hypothesis}"
    )


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


def analyze_transcript_(transcript: str) -> str:
    prompt = f"Analyze this transcript for market intelligence signals:\n\n{transcript}"
    client = get_client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    )
    return format_analysis_output(response.text or "")


def run_analysis_with_progress(transcript: str) -> str:
    show_status("\nTranscript received. Routing analysis request to Gemini...")
    stop_event = threading.Event()
    spinner_thread = threading.Thread(
        target=_spinner,
        args=(stop_event, "Analysis in progress"),
        daemon=True,
    )
    spinner_thread.start()

    try:
        return analyze_transcript_(transcript)
    finally:
        stop_event.set()
        spinner_thread.join()


def main() -> None:
    print("\n=== WTP Signal Extractor ===\n")
    print("Choose input method:")
    print("1 - Youtube URL")
    print("2 - Paste transcript text directly")

    choice = input("\nEnter 1 or 2: ").strip()

    if choice == "1":
        url = normalize_youtube_input(input("Enter Youtube URL: "))
        show_status("\nFetching transcript...")

        try:
            transcript = get_transcript_from_url(url)
            show_status(f"Transcript fetched successfully ({len(transcript)} chars).")
        except Exception as error:
            print(f"Error fetching transcript: {error}")
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

        show_status(f"Transcript captured successfully ({len(transcript)} chars).")

    else:
        print("Invalid choice")
        return

    try:
        result = run_analysis_with_progress(transcript)
        print("\n=== RESULTS ===\n")
        print(safe_console_text(result))
    except Exception as error:
        print(f"Analysis error: {error}")


if __name__ == "__main__":
    main()
