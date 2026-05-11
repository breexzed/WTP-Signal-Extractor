from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def build_output_stem(
    prefix: str = "wtp-analysis",
    session_id: str | None = None,
    timestamp: datetime | None = None,
) -> str:
    stamp = (timestamp or datetime.now()).strftime("%Y%m%d-%H%M%S")
    if session_id:
        return f"{prefix}-{session_id}-{stamp}"
    return f"{prefix}-{stamp}"


def write_artifacts(
    result: dict[str, Any],
    text_report: str,
    output_dir: str | Path = "outputs",
    session_id: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    stem = build_output_stem(session_id=session_id, timestamp=timestamp)
    text_path = output_path / f"{stem}.txt"
    json_path = output_path / f"{stem}.json"

    text_path.write_text(text_report, encoding="utf-8")
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "text_path": str(text_path),
        "json_path": str(json_path),
    }
