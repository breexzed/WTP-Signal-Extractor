from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def sanitize_token(value: str | None, fallback: str = "artifact") -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-.")
    return normalized or fallback


ARTIFACT_SUFFIXES = (".json", ".txt", ".transcript.txt")


def build_output_stem(name: str | None = None, timestamp: datetime | None = None) -> str:
    """Files are named after what they hold: the source or session id, which
    already carries a timestamp. Unnamed output gets wtp-<time>."""
    if name:
        return sanitize_token(name)
    return f"wtp-{(timestamp or datetime.now()).strftime('%Y%m%d-%H%M%S')}"


def unique_stem(output_path: Path, base: str) -> str:
    """base, or base-2, base-3 ... so a rerun never overwrites earlier files."""
    stem, n = base, 2
    while any((output_path / f"{stem}{suffix}").exists() for suffix in ARTIFACT_SUFFIXES):
        stem, n = f"{base}-{n}", n + 1
    return stem


def _write_payload(
    payload: dict[str, Any],
    text_report: str,
    *,
    output_dir: str | Path,
    name: str | None,
    timestamp: datetime | None,
    transcript: str | None = None,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    stem = unique_stem(output_path, build_output_stem(name, timestamp))
    text_path = output_path / f"{stem}.txt"
    json_path = output_path / f"{stem}.json"

    paths = {"text_path": str(text_path), "json_path": str(json_path)}
    if transcript:
        # Saved beside the result so quotes can be re-checked without refetching.
        transcript_path = output_path / f"{stem}.transcript.txt"
        transcript_path.write_text(transcript, encoding="utf-8")
        paths["transcript_path"] = str(transcript_path)
    if isinstance(payload.get("artifacts"), dict):
        payload["artifacts"].update(paths)
    if transcript and isinstance(payload.get("source"), dict):
        payload["source"]["transcript_path"] = paths["transcript_path"]

    text_path.write_text(text_report, encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return paths


def write_artifacts(
    result: dict[str, Any],
    text_report: str,
    output_dir: str | Path = "outputs",
    session_id: str | None = None,
    timestamp: datetime | None = None,
    transcript: str | None = None,
) -> dict[str, str]:
    # session_id here is the artifact's name: the source id for one source.
    return _write_payload(result, text_report, output_dir=output_dir, name=session_id,
                          timestamp=timestamp, transcript=transcript)


def write_session_artifacts(
    session_result: dict[str, Any],
    text_report: str,
    output_dir: str | Path = "outputs",
    session_id: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    return _write_payload(session_result, text_report, output_dir=output_dir, name=session_id,
                          timestamp=timestamp)
