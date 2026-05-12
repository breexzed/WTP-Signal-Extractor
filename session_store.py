from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def sanitize_token(value: str | None, fallback: str = "artifact") -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-.")
    return normalized or fallback


def build_output_stem(
    prefix: str = "wtp-analysis",
    session_id: str | None = None,
    timestamp: datetime | None = None,
) -> str:
    stamp = (timestamp or datetime.now()).strftime("%Y%m%d-%H%M%S-%f")
    if session_id:
        return f"{prefix}-{sanitize_token(session_id)}-{stamp}"
    return f"{prefix}-{stamp}"


def _write_payload(
    payload: dict[str, Any],
    text_report: str,
    *,
    prefix: str,
    output_dir: str | Path,
    session_id: str | None,
    timestamp: datetime | None,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    stem = build_output_stem(prefix=prefix, session_id=session_id, timestamp=timestamp)
    text_path = output_path / f"{stem}.txt"
    json_path = output_path / f"{stem}.json"

    text_path.write_text(text_report, encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "text_path": str(text_path),
        "json_path": str(json_path),
    }


def write_artifacts(
    result: dict[str, Any],
    text_report: str,
    output_dir: str | Path = "outputs",
    session_id: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    return _write_payload(
        result,
        text_report,
        prefix="wtp-analysis",
        output_dir=output_dir,
        session_id=session_id,
        timestamp=timestamp,
    )


def write_session_artifacts(
    session_result: dict[str, Any],
    text_report: str,
    output_dir: str | Path = "outputs",
    session_id: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    return _write_payload(
        session_result,
        text_report,
        prefix="wtp-session-report",
        output_dir=output_dir,
        session_id=session_id,
        timestamp=timestamp,
    )
