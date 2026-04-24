# WTP Signal Extractor

This project is evolving from a single-run transcript analysis CLI into a full market-intelligence research pipeline.

Today, the app can:
- accept a YouTube URL or pasted transcript text
- fetch transcript text when available
- run a two-pass analysis
- normalize the final output into a stable report format

The intended end state is bigger:
- accept many URLs in one run
- process them as a single research session
- extract structured intelligence per source
- produce one consolidated report across all sources
- support Gemini by default, while remaining portable to any OpenAI-compatible model provider later

## Product Direction

The current CLI is useful as a tool.
The full version should behave like a pipeline.

That means the unit of work should no longer be "one video -> one output".
It should become:

`one research session -> many sources -> one structured intelligence package`

In practice, that means:
- a user submits a list of URLs or a session manifest
- the system fetches transcripts for all valid sources
- each source is analyzed independently first
- the individual results are stored as structured artifacts
- a second pass consolidates findings across all sources
- the session ends with one final report that captures patterns, not just isolated observations

This is the difference between a prompt wrapper and a repeatable intelligence pipeline.

## Core Principle

Do not solve multi-source analysis by concatenating many raw transcripts into one giant prompt.

That approach breaks down quickly:
- context windows get consumed by low-value raw text
- failures become all-or-nothing
- retries get expensive
- source attribution becomes weak
- deduplication becomes sloppy
- provider portability becomes harder

The correct architecture is:

`fetch -> normalize -> extract per source -> validate -> aggregate -> render`

## Analysis Model

The system currently runs one model with a structured two-pass prompt:

1. `PASS 1: WILLINGNESS-TO-PAY SIGNALS`
2. `PASS 2: FGP PIPELINE INTELLIGENCE`
3. `COMBINED INTELLIGENCE SUMMARY`

That shape should remain.
What should change is the execution model:

- run the full two-pass extraction per source first
- save the output as structured data
- then run a separate session-level synthesis pass across the extracted objects

This keeps source-level evidence intact while still enabling portfolio-level conclusions.

## What The Full Version Should Do

The pipeline version should support:
- `--url <url>` for quick single-source runs
- `--urls <url1> <url2> <url3>` for small batches
- `--urls-file urls.txt` for research sessions
- `--session session.json` for richer metadata-driven runs

Each session should:
- create a session ID
- deduplicate URLs
- normalize and validate inputs
- fetch transcripts concurrently with bounded parallelism
- save raw transcript artifacts
- analyze each transcript into validated structured data
- aggregate repeated patterns across all sources
- produce a consolidated markdown report and machine-readable JSON

## Why Structured Extraction Matters

If this is done right, the internal source of truth should not be the rendered markdown.
It should be structured data.

The markdown report is only the final presentation layer.

The internal contract should be JSON-like objects such as:
- per-source metadata
- transcript metadata
- pass 1 signals
- pass 2 signals
- combined source summary
- session-level rollups

That enables:
- aggregation
- filtering
- deduplication
- export
- provider swapping
- testability
- future UI or API surfaces

## Recommended Internal Data Shape

Each source result should eventually look conceptually like this:

```json
{
  "source": {
    "url": "https://youtube.com/...",
    "video_id": "abc123",
    "title": "Optional later",
    "transcript_status": "fetched"
  },
  "pass1": {
    "behavior_signals": [],
    "opinion_signals": [],
    "summary": {
      "total_high_signal_moments": 0,
      "dominant_pain_category": "",
      "confidence_level": ""
    }
  },
  "pass2": {
    "cascade_indicators": [],
    "gatekeeper_mentions": [],
    "position_intelligence": [],
    "subniche_culture_signals": [],
    "summary": {
      "strongest_cascade_found": "",
      "highest_signal_gatekeeper_mention": "",
      "position_intelligence_confidence": "",
      "recommended_next_action": ""
    }
  },
  "combined_summary": {
    "top_3_actionable_signals": [],
    "hypothesis_worth_testing": ""
  }
}
```

The session-level aggregate should then combine many of these into:
- repeated WTP themes
- repeated gatekeepers
- strongest cascades across the session
- strongest subniche identity patterns
- top actionable signals across all sources
- one or more testable hypotheses

## Architecture Direction

The current code is intentionally small.
The future version should be split by responsibility.

Recommended layout:

```text
wtp-signal-extractor/
  main.py
  prompt.py
  pyproject.toml
  README.md
  pipeline/
    input.py
    transcripts.py
    schemas.py
    extract.py
    aggregate.py
    render.py
    session_store.py
  providers/
    base.py
    gemini.py
    openai_compatible.py
  reports/
    <session-id>/
      session_report.json
      session_report.md
      sources/
        <source-id>.json
        <source-id>.txt
```

Suggested responsibility split:
- `pipeline/input.py`: parse URLs, files, manifests, dedupe, validate
- `pipeline/transcripts.py`: fetch transcript text and normalize transcript artifacts
- `pipeline/schemas.py`: define structured contracts and validation
- `pipeline/extract.py`: run model extraction per source
- `pipeline/aggregate.py`: consolidate many extracted results into one session view
- `pipeline/render.py`: render markdown, console output, and any future export formats
- `pipeline/session_store.py`: persist artifacts and session metadata
- `providers/base.py`: provider interface
- `providers/gemini.py`: Gemini-specific implementation
- `providers/openai_compatible.py`: generic OpenAI-compatible implementation

## Provider Strategy

The system is Gemini-centric today, but it should not stay Gemini-coupled at the architecture level.

Gemini can remain:
- the default provider
- the first-class tested provider
- the cheapest/fastest starting path

But model access should be abstracted behind one provider interface.

Recommended idea:

```python
class LLMProvider:
    def extract_source(self, transcript: str, prompt: str) -> dict: ...
    def synthesize_session(self, source_results: list[dict], prompt: str) -> dict: ...
```

That way:
- Gemini works through one adapter
- OpenAI-compatible providers work through another adapter
- the pipeline never cares which SDK is underneath

This is important if you want future support for:
- OpenAI
- OpenRouter
- Together
- Groq
- local OpenAI-compatible gateways
- LiteLLM-backed routing

## OpenAI-Compatible Future

If you want this done right, do not treat "OpenAI-compatible" as a future hack.
Design for it now.

The pipeline should support config like:
- `LLM_PROVIDER=gemini`
- `LLM_PROVIDER=openai_compatible`
- `LLM_MODEL_EXTRACTION=...`
- `LLM_MODEL_AGGREGATION=...`
- `LLM_API_KEY=...`
- `LLM_BASE_URL=...`

Then the provider implementation decides how to call the model.

This makes the rest of the codebase provider-agnostic.

## Gemini Guidance

Gemini is a reasonable default for this project.

Why it fits:
- fast enough for transcript extraction workloads
- good price/performance for repeated structured analysis
- strong enough for synthesis if prompts are tight
- easy to prototype through Google AI Studio

### Can the Gemini free model work?

For prototyping and early sessions: yes.

For a serious research pipeline: only for a while.

Free-tier Gemini is useful for:
- local experiments
- prompt tuning
- testing source-level extraction
- small batches

Free-tier Gemini is not a great long-term production assumption for:
- large research sessions
- reliable batch throughput
- predictable scaling
- privacy-sensitive workflows

Practical recommendation:
- start with Gemini Flash for source extraction
- consider a stronger model for session synthesis if needed
- do not design the system around free-tier assumptions

If this becomes a real workflow, assume you will eventually need:
- paid usage
- higher rate limits
- better operational control
- batching or caching features

## Model Strategy

Do not force one model to do everything.

The ideal setup uses two roles:

1. Extraction model
- cheap
- fast
- consistent
- used many times per session

2. Aggregation model
- stronger reasoning
- used once or a few times per session
- consolidates repeated patterns across sources

Good strategy:
- source extraction: cheaper model
- session synthesis: stronger model

This keeps session costs sane while improving overall output quality.

## Prompting Strategy

The current project uses a strong prompt and a normalization layer.
That is good for now.

But the perfect version should move toward:
- structured extraction prompts
- schema-validated outputs
- strict render-time formatting

The model should ideally return structured objects, not freeform markdown.

Then the app can:
- validate fields
- fill missing defaults
- drop malformed sections
- render perfectly every time

This is much more reliable than trusting the model to format markdown exactly forever.

## Output Strategy

Every session should produce both:
- a machine-readable artifact
- a human-readable artifact

Recommended outputs:
- `session_report.json`
- `session_report.md`
- optional per-source JSON and transcript snapshots

The JSON should be the canonical source of truth.
The markdown should be a rendered view of that JSON.

## Batch Processing Principles

When adding multi-URL support, do it with care:

- validate all inputs before expensive model calls
- deduplicate URLs before fetching transcripts
- keep per-source failures isolated
- never let one transcript failure kill the whole session
- use bounded concurrency
- preserve source attribution for every extracted signal
- make retries source-specific
- cache transcript fetches where possible
- store intermediate artifacts for debugging

If one out of ten transcripts fails, the session should still finish and report:
- what succeeded
- what failed
- why it failed

## Aggregation Principles

The aggregation pass should not simply summarize everything vaguely.
It should look for:
- repeated pain categories
- repeated gatekeepers
- repeated downstream failures
- repeated differentiation claims
- contradictions between sources
- strongest signals by severity and recurrence

The goal is not only "what was said".
The goal is:
- what repeated
- what matters most
- what appears structurally important
- what suggests a product or distribution move

## Reliability Requirements

If this is to be done right, the system should be built with these quality rules:

- preserve exact quote attribution
- never merge sources without keeping source references
- store raw transcripts separately from extracted findings
- validate model outputs before aggregation
- normalize all final reports through one renderer
- treat the JSON artifact as canonical
- allow rerunning only failed sources
- keep model provider logic isolated from pipeline logic
- make output reproducible enough for review

## Failure Handling

The pipeline should classify failures explicitly:
- invalid URL
- transcript unavailable
- transcript fetch blocked
- provider rate limit
- provider timeout
- malformed model output
- aggregation failure

This should appear in session output rather than failing silently.

## Security And Secrets

Do not commit secrets.

The repo should continue to ignore:
- `.env`
- `.env.*`
- `.venv/`
- generated caches

Provider credentials should always come from environment variables.

## Current State Of This Repo

Right now the repo provides:
- a working CLI
- transcript fetching
- Gemini-based two-pass analysis
- output normalization
- Windows-safe console rendering
- tests for core formatting and flow

This is a strong prototype foundation.
It is not yet the final pipeline architecture.

## Recommended Implementation Order

If building this properly from here, the order should be:

1. Add session-based input
- support many URLs in one run
- accept file-based input
- create a session ID

2. Introduce structured source result schemas
- stop treating markdown as the internal source of truth
- store validated per-source objects

3. Split provider code from pipeline code
- keep Gemini as default
- add an OpenAI-compatible provider interface

4. Add session aggregation
- aggregate structured results, not raw transcripts

5. Persist artifacts
- save source-level and session-level JSON
- render session markdown from JSON

6. Add retries, partial failure handling, and bounded concurrency

7. Add alternative providers
- OpenAI-compatible path first
- optional routing layer later

## What "Done Right" Looks Like

If this project is built perfectly, it should feel like this:

- one command starts a whole research session
- every source is traceable
- the model can change without rewriting the pipeline
- the outputs are structured enough for automation
- the markdown is clean enough for human review
- failures are isolated, visible, and recoverable
- aggregation surfaces what is repeated and strategic, not just what is interesting

That is the target.

## Setup

1. Add a model API key to `.env`.

For Gemini today:
- `GEMINI_API_KEY=your_key`
- or `GOOGLE_API_KEY=your_key`

2. Run the app:
- `uv run python main.py`
- or `.venv\Scripts\python.exe main.py`

## Notes

- The YouTube flow requires a video with an available transcript.
- If you paste a larger note containing multiple YouTube links, the CLI will use the first valid YouTube URL it finds.
- The project uses the current `google-genai` SDK rather than the deprecated `google.generativeai` package.
- The CLI shows status updates after transcript capture, before routing to the model, and during active analysis.
- Final console output is normalized before display so formatting stays stable even when the model drifts.
