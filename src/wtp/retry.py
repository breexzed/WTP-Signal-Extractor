"""Retry transient failures (rate limits, 5xx, timeouts, dropped connections) with
exponential backoff. Permanent failures (bad key, no captions, invalid video) fail
on the first attempt: retrying them only burns time and quota.

Settings (environment): WTP_MAX_ATTEMPTS (default 3), WTP_RETRY_BASE_DELAY seconds
(default 2; delays are base, 2*base, 4*base ... plus up to 25% jitter).
"""
from __future__ import annotations

import os
import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")

TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}

# Names, not imports, so this module works whichever SDKs are installed.
TRANSIENT_TYPES = {
    "TimeoutError", "ConnectionError", "ConnectionResetError",
    "APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError",  # openai
    "ServerError",                                                                    # google-genai
    "ConnectTimeout", "ReadTimeout", "ConnectError", "RemoteProtocolError",          # httpx
    "YouTubeRequestFailed",                                                           # youtube 5xx/network
    "MalformedModelOutput",                                                           # ours: bad JSON once
}
# IpBlocked/RequestBlocked: YouTube blocks for hours, not seconds. Fail fast.
PERMANENT_TYPES = {"IpBlocked", "RequestBlocked", "TranscriptsDisabled", "NoTranscriptFound",
                   "VideoUnavailable", "VideoUnplayable", "InvalidVideoId", "AgeRestricted",
                   "PoTokenRequired"}


class MalformedModelOutput(RuntimeError):
    """The model returned text that is not the JSON the schema demands."""


def status_code(error: BaseException) -> int | None:
    for attr in ("status_code", "code", "status"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def is_transient(error: BaseException) -> bool:
    names = {cls.__name__ for cls in type(error).__mro__}
    if names & PERMANENT_TYPES:
        return False
    code = status_code(error)
    if code is not None:
        return code in TRANSIENT_STATUS
    return bool(names & TRANSIENT_TYPES)


def max_attempts() -> int:
    return max(1, int(os.getenv("WTP_MAX_ATTEMPTS", "3")))


def base_delay() -> float:
    return max(0.0, float(os.getenv("WTP_RETRY_BASE_DELAY", "2")))


def with_retries(
    fn: Callable[[], T],
    *,
    what: str,
    log: Callable[[str], None],
    attempts: int | None = None,
) -> tuple[T, int]:
    """Run fn until it succeeds, a permanent error occurs, or attempts run out.
    Returns (value, attempts used). Re-raises the last error, annotated with the
    attempt count in `error.wtp_attempts`."""
    limit = attempts or max_attempts()
    for attempt in range(1, limit + 1):
        try:
            return fn(), attempt
        except Exception as error:
            error.wtp_attempts = attempt
            if attempt == limit or not is_transient(error):
                raise
            delay = base_delay() * 2 ** (attempt - 1)
            delay += random.uniform(0, delay * 0.25)
            detail = " ".join(str(error).split())[:160]
            log(f"{what}: {type(error).__name__} ({status_code(error) or 'no status'}: {detail}); "
                f"retry {attempt + 1}/{limit} in {delay:.1f}s")
            time.sleep(delay)
    raise AssertionError("unreachable")
