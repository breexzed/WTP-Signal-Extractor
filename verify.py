"""Check every quote the model returned against the transcript it was given.

The prompt says "exact words from transcript", but nothing enforced it. An
agent citing a quote needs to know whether the speaker actually said it.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

# Share of the quote's words that must appear, in order, in one stretch of
# the transcript. One changed word in a 25-word quote scores 0.96.
APPROXIMATE_RATIO = 0.8
QUOTE_STATUSES = ("verified", "approximate", "stitched", "not_found")

# (section path, list key, quote field)
QUOTE_FIELDS = [
    ("pass1", "behavior_signals", "QUOTE"),
    ("pass1", "opinion_signals", "QUOTE"),
    ("pass2", "cascade_indicators", "QUOTE"),
    ("pass2", "gatekeeper_mentions", "QUOTE"),
    ("pass2", "position_intelligence", "QUOTE"),
    ("pass2", "subniche_culture_signals", "QUOTE"),
    ("diagnostics", "named_entities", "supporting_quote"),
    ("diagnostics", "gatekeepers", "supporting_quote"),
]


def normalize(text: str) -> str:
    """Lowercase, unify quotes/dashes, drop punctuation, collapse whitespace."""
    text = text.lower()
    text = text.translate(str.maketrans({"’": "'", "‘": "'", "“": '"',
                                         "”": '"', "—": " ", "–": " "}))
    text = re.sub(r"[^\w\s']", " ", text)
    text = text.replace("'", "")
    return " ".join(text.split())


def match_quote(quote: str, transcript_words: list[str], transcript_norm: str,
                matcher: SequenceMatcher) -> tuple[str, float]:
    """matcher holds the transcript words as seq2, so its index is built once."""
    q = normalize(quote)
    if not q:
        return "not_found", 0.0
    if q in transcript_norm:
        return "verified", 1.0
    words = q.split()
    # Each run of quote words found verbatim proposes where the quote sits in
    # the transcript. The longest run alone can point at the wrong place (a
    # phrase like "I had to be like" said twice), so score every candidate
    # and keep the best alignment. One changed word costs one word.
    matcher.set_seq1(words)
    offsets = set()
    for start in range(len(words)):
        anchor = matcher.find_longest_match(start, len(words), 0, len(transcript_words))
        if anchor.size >= min(2, len(words)):
            offsets.add(anchor.b - anchor.a)
    ratio = 0.0
    for offset in offsets:
        lo, hi = max(0, offset - len(words)), offset + 2 * len(words)
        window = SequenceMatcher(None, words, transcript_words[lo:hi], autojunk=False)
        matched = sum(m.size for m in window.get_matching_blocks())
        ratio = max(ratio, round(matched / len(words), 3))
    if ratio >= APPROXIMATE_RATIO:
        return "approximate", ratio
    return "not_found", ratio


def fragments(quote: str) -> list[str]:
    """Split on ellipses and sentence ends; keep pieces of 3+ words."""
    parts = re.split(r"\.\.\.|\u2026|(?<=[.!?])\s+", quote)
    return [p for p in parts if len(p.split()) >= 3]


def classify(quote: str, transcript_words, transcript_norm, matcher) -> tuple[str, float]:
    status, ratio = match_quote(quote, transcript_words, transcript_norm, matcher)
    if status != "not_found":
        return status, ratio
    # Real sentences joined from different places (or reordered) are not
    # invented, but they are not one continuous quote either.
    pieces = fragments(quote)
    if len(pieces) > 1 and all(
        match_quote(piece, transcript_words, transcript_norm, matcher)[0] != "not_found"
        for piece in pieces
    ):
        return "stitched", ratio
    return status, ratio


def verify_quotes(result: dict[str, Any], transcript: str | None) -> dict[str, Any]:
    if not transcript:
        return {"checked": False, "reason": "No transcript available to check against.",
                "total": 0, **{s: 0 for s in QUOTE_STATUSES}, "items": []}

    transcript_norm = normalize(transcript)
    transcript_words = transcript_norm.split()
    matcher = SequenceMatcher(None, [], transcript_words, autojunk=False)
    items = []
    for section, key, field in QUOTE_FIELDS:
        for index, signal in enumerate(result.get(section, {}).get(key, []) or []):
            quote = str(signal.get(field) or "").strip().strip('"“”')
            if not quote:
                continue
            status, ratio = classify(quote, transcript_words, transcript_norm, matcher)
            items.append({"path": f"{section}.{key}[{index}].{field}", "quote": quote,
                          "status": status, "match_ratio": ratio})

    counts = {s: sum(i["status"] == s for i in items) for s in QUOTE_STATUSES}
    return {"checked": True, "total": len(items), **counts, "items": items}
