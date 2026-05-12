# WTP Signal Extractor

WTP Signal Extractor is a Gemini-first Python CLI that analyzes transcript sources and produces:
- a human-readable report for terminal review
- a canonical JSON artifact for downstream systems

The repo is no longer just a formatting wrapper around a transcript prompt.
It now acts as the structured evaluator and diagnostics half of a future closed-loop system with `source-garden-intelligence`.

## What The Repo Does Today

The current implementation supports:
- YouTube URL input
- pasted transcript input
- multi-URL batch input through CLI flags
- optional JSON session manifest input
- transcript fetching through `youtube-transcript-api`
- Gemini analysis using a structured multi-pass prompt
- Windows-safe terminal rendering
- text artifact persistence
- canonical JSON artifact persistence
- parse warnings and raw-output preservation
- Source Garden-compatible diagnostics
- session-wide aggregation and consolidated reporting

The current unit of work can now be either:
- a single interactive source run
- a multi-source batch session over YouTube URLs
- a manifest-driven session run with optional Source Garden context

This repo still does **not** yet implement concurrent transcript fetching.

## Compatibility Goal

This repo is designed to interoperate later with `source-garden-intelligence` without creating a hardcoded cross-repo dependency.

The intended relationship is:
- Source Garden decides where to look
- WTP decides what was actually found and what to do next

That means WTP now emits structured diagnostics that can eventually help Source Garden answer:
- which registers underperformed
- which gatekeeper types appeared
- which source types produced the strongest signals
- what search language was too generic
- what named entities started recurring

## Current Status

This repo is currently:
- a working CLI
- a per-source structured extractor
- a diagnostic producer for future loop feedback
- a JSON-first artifact generator
- a provider-abstracted model caller with Gemini and OpenAI-compatible adapters
- a batch-capable session runner for YouTube sources
- a manifest-capable session runner with optional Source Garden-compatible metadata

This repo is **not yet**:
- a session-context collection CLI like Source Garden
- a fully schema-enforced LLM output system

## Architecture

Current file responsibilities:

- [main.py](C:/Users/Owl/playbook/wtp-signal-extractor/main.py): CLI orchestration, interactive/batch/manifest input handling, provider-routed model calls, progress spinner, failure handling, per-source and session artifact persistence
- [prompt.py](C:/Users/Owl/playbook/wtp-signal-extractor/prompt.py): system prompt for the two-pass extraction plus diagnostics sections
- [schemas.py](C:/Users/Owl/playbook/wtp-signal-extractor/schemas.py): canonical result shape and allowed vocabularies
- [extract.py](C:/Users/Owl/playbook/wtp-signal-extractor/extract.py): raw model-output parsing into structured sections
- [diagnostics.py](C:/Users/Owl/playbook/wtp-signal-extractor/diagnostics.py): diagnostic derivation, normalization, register alignment, entity/gatekeeper heuristics
- [render.py](C:/Users/Owl/playbook/wtp-signal-extractor/render.py): human-readable report rendering
- [session_store.py](C:/Users/Owl/playbook/wtp-signal-extractor/session_store.py): text/JSON artifact writing
- [aggregate.py](C:/Users/Owl/playbook/wtp-signal-extractor/aggregate.py): aggregate rollups across one or more source results
- [providers/base.py](C:/Users/Owl/playbook/wtp-signal-extractor/providers/base.py): provider config and interface contract
- [providers/gemini.py](C:/Users/Owl/playbook/wtp-signal-extractor/providers/gemini.py): Gemini adapter
- [providers/openai_compatible.py](C:/Users/Owl/playbook/wtp-signal-extractor/providers/openai_compatible.py): OpenAI-compatible adapter using the official OpenAI Python SDK
- [test_main.py](C:/Users/Owl/playbook/wtp-signal-extractor/test_main.py): parser, diagnostics, persistence, mocked CLI, and aggregation tests

## Runtime Flow

Each run currently follows one of three shapes:

1. Accept one source interactively:
- YouTube URL
- or pasted transcript text

2. Accept many YouTube URLs non-interactively:
- `--urls`
- `--urls-file`

3. Accept a JSON session manifest:
- `--session`
- optional Source Garden context
- one or more sources containing `url` and/or `transcript`

4. Build source metadata:
- `source_id`
- URL/video information if present
- transcript status
- provenance placeholders

5. Run the configured provider against the structured market-intelligence prompt.
   The model call now goes through a provider abstraction layer.

6. Parse the model output into:
- Pass 1
- Pass 2
- combined summary
- diagnostics hints

7. Derive structured diagnostics:
- named entities
- gatekeepers
- phase fit
- register alignment
- search-language feedback
- recommended next phase

8. Render readable text output:
- per-source reports for single-source runs
- a session-wide synthesis report for batch runs

9. Persist JSON-first artifacts:
- one `.txt` and one `.json` per source
- one `.txt` and one `.json` session report per batch run
- one `.txt` and one `.json` session report per manifest run

## Input Modes

### YouTube URL

The CLI accepts one YouTube URL, extracts the video ID, fetches the transcript, and analyzes it.

Supported URL forms include:
- `https://www.youtube.com/watch?v=...`
- `https://youtu.be/...`

If transcript fetching fails:
- the CLI still produces a visible failure result
- the failure is persisted as a structured artifact
- the run does not fail silently

### Pasted Transcript

The CLI accepts manual transcript paste input line-by-line until the user enters `End`.

The pasted flow preserves the same analysis and artifact-writing behavior as the YouTube path.

### Batch URL CLI

The CLI also accepts many YouTube URLs in one run:

```powershell
uv run python main.py --urls https://youtu.be/... https://www.youtube.com/watch?v=...
```

or from a file:

```powershell
uv run python main.py --urls-file urls.txt
```

Batch mode currently:
- normalizes and deduplicates URLs
- processes each source serially
- writes one per-source text artifact and one per-source JSON artifact
- aggregates the resulting source diagnostics into one session summary
- writes one session text artifact and one session JSON artifact

Batch mode is intentionally visible about failures.
If one source fails transcript fetch or analysis, that source still gets a structured failure artifact and the rest of the session continues.

### Session Manifest CLI

The CLI also accepts a JSON session manifest:

```powershell
uv run python main.py --session session.json
```

Manifest mode is optional, not required for core use. If no Source Garden data is present, the tool still works as long as the manifest contains a `sources` list.

A minimal manifest can be:

```json
{
  "sources": [
    {
      "url": "https://youtu.be/dQw4w9WgXcQ"
    },
    {
      "transcript": "We paid for two tools and still depend on Zocdoc."
    }
  ]
}
```

A richer manifest can carry future loop metadata:

```json
{
  "session_id": "research-session-1",
  "session_context": {
    "vertical": "dental",
    "operator_type": "clinic_owner",
    "targeted_subniche": "premium_clinic",
    "fgp_phase": "3",
    "gatekeeper_type": "Type4",
    "currency_window": "2026-Q2",
    "session_date": "2026-05-11",
    "prior_loop_map_phase": "2"
  },
  "sources": [
    {
      "source_id": "source-url-1",
      "url": "https://youtu.be/dQw4w9WgXcQ",
      "provenance": {
        "origin_cluster_id": "cluster-1",
        "origin_register": "complaint_register",
        "query_used": "premium clinic booking dependency"
      }
    }
  ]
}
```

Manifest mode currently:
- accepts source-level `url` or `transcript`
- accepts optional source-level `source_id`
- accepts optional source-level `provenance`
- accepts optional session-level `session_context`
- writes artifacts under `reports/<session-id>/`
- keeps working even when all Source Garden-specific fields are absent

## Prompt Shape

The current prompt preserves these major sections:

- `PASS 1: WILLINGNESS-TO-PAY SIGNALS`
- `PASS 2: FGP PIPELINE INTELLIGENCE`
- `COMBINED INTELLIGENCE SUMMARY`

It also asks the model for structured diagnostics support blocks:
- source diagnostics
- named entities
- gatekeeper objects
- register alignment
- search language feedback
- diagnostic notes

The parser does **not** trust the model completely.
It treats the model output as recoverable-but-fallible input.

## Canonical Output Contract

Each run produces a canonical per-source JSON object with this top-level shape:

```json
{
  "source": {},
  "provenance": {},
  "pass1": {},
  "pass2": {},
  "diagnostics": {},
  "combined_summary": {},
  "parse_warnings": [],
  "raw_output": "..."
}
```

### `source`

Includes:
- `source_id`
- `url`
- `video_id`
- `input_type`
- `transcript_status`
- `source_type`
- `speaker_type`

Allowed `input_type` values:
- `youtube_url`
- `pasted_transcript`

Allowed `transcript_status` values:
- `fetched`
- `pasted`
- `failed`

Allowed `source_type` values:
- `operator_interview`
- `panel`
- `vendor_demo`
- `trade_discussion`
- `unknown`

Allowed `speaker_type` values:
- `operator`
- `intermediary`
- `mixed`
- `unknown`

### `provenance`

Includes:
- `origin_cluster_id`
- `origin_register`
- `query_used`

These are placeholders today and are usually `null` in the CLI.
They exist so Source Garden can supply them later without redesigning the contract.

### `pass1`

Includes:
- `behavior_signals`
- `opinion_signals`
- `summary`

This is the WTP-focused half of the output.

### `pass2`

Includes:
- `cascade_indicators`
- `gatekeeper_mentions`
- `position_intelligence`
- `subniche_culture_signals`
- `summary`

This is the FGP pipeline-intelligence half of the output.

### `diagnostics`

Includes:
- `phase_fit`
- `signal_density`
- `register_alignment`
- `named_entities`
- `gatekeepers`
- `search_language_feedback`
- `recommended_next_phase`
- `diagnostic_notes`

### `combined_summary`

Includes:
- `top_3_actionable_signals`
- `hypothesis_worth_testing`

### `parse_warnings`

Explicitly records parser drift or structural recovery concerns.

### `raw_output`

Preserves the original model output for debugging and auditability.

## Diagnostics Behavior

The diagnostics layer is intentionally conservative.

It prefers:
- explicit transcript evidence
- explicit model-provided support
- fallbacks only when needed

It avoids:
- inventing named entities
- inventing register names
- pretending uncertainty does not exist

### Phase Fit

`phase_fit` can be:
- `0`
- `1`
- `2`
- `3`
- `3.5`
- `mixed`
- `unknown`

It is inferred from the parsed content when the model does not provide a clean answer.

### Signal Density

`signal_density` can be:
- `low`
- `medium`
- `high`

It is derived from the amount of usable structured signal recovered from the source.

### Named Entities

Each named entity object includes:
- `name`
- `entity_kind`
- `relationship`
- `supporting_quote`
- `confidence`

Allowed `entity_kind` values:
- `platform`
- `software`
- `institution`
- `distributor`
- `person`
- `certification_body`
- `other`

Allowed `relationship` values:
- `dependent`
- `frustrated`
- `switching`
- `praise`
- `unknown`

If the model does not provide entity objects, some entities can be derived from gatekeeper mentions.
If evidence is weak, entities should be omitted rather than guessed.

### Gatekeepers

Each gatekeeper object includes:
- `entity`
- `dependency_type`
- `gatekeeper_type`
- `operator_relationship`
- `supporting_quote`
- `confidence`

Allowed `dependency_type` values:
- `structural_friction`
- `social_authority`
- `information_asymmetry`
- `platform`
- `unknown`

Allowed `gatekeeper_type` values:
- `Type1`
- `Type2`
- `Type3`
- `Type4`
- `unknown`

The type mapping is Source Garden-compatible:
- `Type1`: owns a process others cannot bypass
- `Type2`: their word moves the network
- `Type3`: controls information others need
- `Type4`: platform controlling access to customers

Allowed `operator_relationship` values:
- `dependent`
- `frustrated`
- `loyal`
- `switching_away`
- `unknown`

### Register Alignment

Register alignment uses **only** the Source Garden-compatible register names:

- `operator_vernacular`
- `industry_professional`
- `complaint_register`
- `consequence_register`
- `intermediary_register`
- `trade_publication`
- `job_listing_register`
- `year_specific`
- `gatekeeper_self_description`

No new register names are invented.

Each register-alignment object includes:
- `register`
- `matched_signals`
- `strength`

### Search Language Feedback

This object includes:
- `likely_too_generic`
- `too_vendor_heavy`
- `off_phase`
- `likely_operator_facing`
- `likely_gatekeeper_facing`
- `reason`

This is heuristic today.
It is meant to feed future loop correction, not to act as absolute truth.

## Aggregation

This repo now includes session-compatible aggregation in [aggregate.py](C:/Users/Owl/playbook/wtp-signal-extractor/aggregate.py:1).

It can aggregate one or more source results into:
- `session_id`
- `source_count`
- `register_performance`
- `gatekeeper_type_distribution`
- `recurring_entities`
- `source_type_performance`
- `query_feedback`
- `recommended_next_phase`
- `aggregate_notes`

This is now exposed through the batch CLI path and is still reusable programmatically.

## Artifact Writing

Each run writes:
- a rendered text report
- a canonical JSON artifact

Default output directories:
- `outputs/`
- `reports/<session-id>/` for manifest-driven session runs

Naming pattern:
- `wtp-analysis-<timestamp>.txt`
- `wtp-analysis-<timestamp>.json`
- `wtp-session-report-<session-id>-<timestamp>.txt`
- `wtp-session-report-<session-id>-<timestamp>.json`

In batch mode, per-source artifacts are also given stable source-based IDs so multiple sources processed in the same second do not collide.
In manifest mode, the session report and per-source artifacts live together under a dedicated session directory.

JSON is the source of truth.
The text file is the presentation layer.

## Failure Philosophy

This repo follows the same general philosophy as Source Garden:
- no silent failure
- preserve raw output when parsing breaks
- emit parse warnings explicitly
- keep malformed sections visible
- salvage what can be salvaged

Failure states are represented as structured outputs, not just terminal messages.

Examples:
- invalid YouTube URL
- transcript fetch failure
- parse drift
- model failure

## Current CLI Behavior

The interactive flow is still simple:

1. choose input method
2. provide one source
3. wait for analysis
4. review rendered report in terminal
5. inspect saved `.txt` and `.json` artifacts

The CLI also still provides:
- transcript status messages
- a routing message before the model call
- a spinner during active analysis

The non-interactive batch flow is:

1. pass `--urls` and/or `--urls-file`
2. process each YouTube source in sequence
3. persist per-source artifacts
4. render and persist one consolidated session report

The manifest flow is:

1. pass `--session session.json`
2. load optional session context and source-level provenance
3. process each source in sequence
4. persist per-source artifacts into `reports/<session-id>/`
5. render and persist one consolidated session report in that same directory

## Setup

Create `.env` with one valid API key:

```env
GEMINI_API_KEY=your_key_here
```

or:

```env
GOOGLE_API_KEY=your_key_here
```

Optional provider selection:

```env
LLM_PROVIDER=gemini
GEMINI_MODEL_NAME=gemini-2.5-flash
```

For an OpenAI-compatible backend:

```env
LLM_PROVIDER=openai_compatible
OPENAI_COMPATIBLE_API_KEY=your_key_here
OPENAI_COMPATIBLE_BASE_URL=https://your-provider.example/v1
OPENAI_COMPATIBLE_MODEL_NAME=your-model-name
```

Install dependencies:

```powershell
uv sync
```

Run the CLI:

```powershell
uv run python main.py
```

or:

```powershell
.\.venv\Scripts\python.exe main.py
```

Run batch mode:

```powershell
uv run python main.py --urls https://youtu.be/... https://www.youtube.com/watch?v=...
```

or:

```powershell
uv run python main.py --urls-file urls.txt
```

Run manifest mode:

```powershell
uv run python main.py --session session.json
```

## Dependencies

Current runtime dependencies from [pyproject.toml](C:/Users/Owl/playbook/wtp-signal-extractor/pyproject.toml:1):
- `google-genai`
- `openai`
- `python-dotenv`
- `youtube-transcript-api`

Python target:
- `>=3.14`

## Testing

The current test suite lives in [test_main.py](C:/Users/Owl/playbook/wtp-signal-extractor/test_main.py:1).

It currently covers:
- structured parsing
- fallback parsing behavior
- entity extraction structure
- gatekeeper classification structure
- register alignment validity
- JSON artifact writing
- session artifact writing
- mocked single-source CLI flow
- mocked batch CLI flow
- mocked manifest CLI flow
- aggregation behavior
- provider selection behavior
- console-output normalization
- transcript fetch behavior

Run tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

## Current Limitations

These are real current limitations, not future aspirations:

- pasted transcripts are still single-source only
- no hard cross-repo integration with Source Garden exists yet
- batch processing is serial, not concurrent
- diagnostics are partly heuristic
- the parser still depends on the model broadly respecting the requested structure
- manifest validation is intentionally light and permissive

## What The Previous README Claimed That Is Not Yet Implemented

The previous README described several future-state capabilities that do **not** exist in the repo today:

- concurrent transcript fetching across many sources
- `pipeline/` and `providers/` directory layouts

Those ideas may still be good future direction, but they were not accurate descriptions of the current codebase.

## Repo Hygiene Notes

Ignored local/runtime artifacts include:
- `.env`
- `.env.*`
- `.venv/`
- `__pycache__/`
- `outputs/`
- `reports/`
- `.uv-cache/`
- `tmp*/`

## Summary

The repo today is best described as:
- a working single-source research CLI
- a working batch research CLI for YouTube sources
- a working manifest-driven session CLI
- a Gemini-first structured evaluator
- a Source Garden-compatible diagnostics producer
- a JSON-first artifact generator

It is already useful as the evaluator side of a closed-loop system.
It is not yet the full manifest-driven orchestration layer.
