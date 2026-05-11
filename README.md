# WTP Signal Extractor

WTP Signal Extractor is a Gemini-first Python CLI that analyzes a single transcript source at a time and produces:
- a human-readable report for terminal review
- a canonical JSON artifact for downstream systems

The repo is no longer just a formatting wrapper around a transcript prompt.
It now acts as the structured evaluator and diagnostics half of a future closed-loop system with `source-garden-intelligence`.

## What The Repo Does Today

The current implementation supports:
- YouTube URL input
- pasted transcript input
- transcript fetching through `youtube-transcript-api`
- Gemini analysis using a structured multi-pass prompt
- Windows-safe terminal rendering
- text artifact persistence
- canonical JSON artifact persistence
- parse warnings and raw-output preservation
- Source Garden-compatible diagnostics and aggregation stubs

The current unit of work is still a single source run.
This repo does **not** yet implement multi-URL batch ingestion or a full research-session CLI.

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

This repo is **not yet**:
- a multi-source batch pipeline
- a session-context collection CLI like Source Garden
- a provider-agnostic model layer
- a fully schema-enforced LLM output system

## Architecture

Current file responsibilities:

- [main.py](C:/Users/Owl/playbook/wtp-signal-extractor/main.py): CLI orchestration, input handling, Gemini call, progress spinner, failure handling, artifact persistence
- [prompt.py](C:/Users/Owl/playbook/wtp-signal-extractor/prompt.py): system prompt for the two-pass extraction plus diagnostics sections
- [schemas.py](C:/Users/Owl/playbook/wtp-signal-extractor/schemas.py): canonical result shape and allowed vocabularies
- [extract.py](C:/Users/Owl/playbook/wtp-signal-extractor/extract.py): raw model-output parsing into structured sections
- [diagnostics.py](C:/Users/Owl/playbook/wtp-signal-extractor/diagnostics.py): diagnostic derivation, normalization, register alignment, entity/gatekeeper heuristics
- [render.py](C:/Users/Owl/playbook/wtp-signal-extractor/render.py): human-readable report rendering
- [session_store.py](C:/Users/Owl/playbook/wtp-signal-extractor/session_store.py): text/JSON artifact writing
- [aggregate.py](C:/Users/Owl/playbook/wtp-signal-extractor/aggregate.py): aggregate rollups across one or more source results
- [test_main.py](C:/Users/Owl/playbook/wtp-signal-extractor/test_main.py): parser, diagnostics, persistence, mocked CLI, and aggregation tests

## Runtime Flow

Each run currently follows this flow:

1. Accept one source:
- YouTube URL
- or pasted transcript text

2. Build source metadata:
- `source_id`
- URL/video information if present
- transcript status
- provenance placeholders

3. Run Gemini against the structured market-intelligence prompt.

4. Parse the model output into:
- Pass 1
- Pass 2
- combined summary
- diagnostics hints

5. Derive structured diagnostics:
- named entities
- gatekeepers
- phase fit
- register alignment
- search-language feedback
- recommended next phase

6. Render a readable text report.

7. Persist both:
- `.txt`
- `.json`

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

This repo now includes a session-compatible aggregation stub in [aggregate.py](C:/Users/Owl/playbook/wtp-signal-extractor/aggregate.py:1).

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

This is not yet exposed as a multi-source CLI workflow.
It is currently a programmatic path intended for future integration.

## Artifact Writing

Each run writes:
- a rendered text report
- a canonical JSON artifact

Default output directory:
- `outputs/`

Naming pattern:
- `wtp-analysis-<timestamp>.txt`
- `wtp-analysis-<timestamp>.json`

If a session ID is supplied programmatically, it becomes part of the filename.

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

## Setup

Create `.env` with one valid API key:

```env
GEMINI_API_KEY=your_key_here
```

or:

```env
GOOGLE_API_KEY=your_key_here
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

## Dependencies

Current runtime dependencies from [pyproject.toml](C:/Users/Owl/playbook/wtp-signal-extractor/pyproject.toml:1):
- `google-genai`
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
- mocked CLI flow
- aggregation behavior
- console-output normalization
- transcript fetch behavior

Run tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

## Current Limitations

These are real current limitations, not future aspirations:

- only one source can be entered interactively per run
- no batch URL ingestion exists yet
- no session manifest ingestion exists yet
- no OpenAI-compatible provider path exists yet
- no provider abstraction layer exists yet
- no hard cross-repo integration with Source Garden exists yet
- diagnostics are partly heuristic
- the parser still depends on the model broadly respecting the requested structure
- aggregation exists as a function, not yet as a full session CLI

## What The Previous README Claimed That Is Not Yet Implemented

The previous README described several future-state capabilities that do **not** exist in the repo today:

- multi-URL CLI batch support
- session manifest support
- concurrent transcript fetching across many sources
- provider abstraction with Gemini and OpenAI-compatible adapters
- `pipeline/` and `providers/` directory layouts
- session-wide synthesis over many fetched sources as a user-facing CLI flow
- per-session report directories like `reports/<session-id>/...`

Those ideas may still be good future direction, but they were not accurate descriptions of the current codebase.

## Repo Hygiene Notes

Ignored local/runtime artifacts include:
- `.env`
- `.env.*`
- `.venv/`
- `__pycache__/`
- `outputs/`
- `.uv-cache/`
- `tmp*/`

## Summary

The repo today is best described as:
- a working single-source research CLI
- a Gemini-first structured evaluator
- a Source Garden-compatible diagnostics producer
- a JSON-first artifact generator

It is already useful as the evaluator side of a closed-loop system.
It is not yet the full multi-source orchestration layer.
