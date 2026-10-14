# AGENTS.md — WTP Signal Extractor

You (an AI agent) are the main user of this CLI. This file plus `wtp --describe`
is everything you need. If something you needed was missing, add it here.

## What it does
Takes a transcript (YouTube URL, text file, stdin, or a session manifest of many sources),
asks an LLM for two passes of market signals as **schema-enforced JSON**
(`model_output.MODEL_OUTPUT_SCHEMA`), then checks the answer locally:
- **Pass 1, WTP (willingness to pay):** behavior signals (money spent, tools abandoned,
  workarounds, urgency) are strong; opinion signals (wishes, hypotheticals) are weak.
- **Pass 2, FGP pipeline:** cascades (phase 2), gatekeepers (phase 3), what gatekeepers
  protect (phase 3.5), sub-niche identity (phase 0).
- **Local checks (no model):** every quote is matched against the transcript
  (`evidence`), every diagnostic says whether the model or a heuristic produced it
  (`diagnostics.field_sources`).

Full domain glossary (phases, gatekeeper Type1–4, registers, Source Garden): `--describe` → `domain`.

## Run it
Installed: `wtp` (from `uv tool install git+https://github.com/breexzed/WTP-Signal-Extractor@<tag>`).
From a checkout: `uv run wtp`. Config: real env vars, then `./.env`, then `~/.config/wtp/.env`.
Runs are saved under `~/.local/share/wtp/` unless `--out-dir`. `wtp --check` shows all of this.

```bash
wtp --describe                          # full contract as JSON, no network
wtp --check                             # config preflight as JSON, no network; exit 2 = fix config
wtp --url "https://youtu.be/ID" --json  # one video
wtp --transcript-file notes.txt --json  # a file; use '-' for stdin
wtp --urls URL1 URL2 --json             # several videos, one session
wtp --session manifest.json --json      # manifest (see --describe → manifest_example)
wtp --replay raw.txt --transcript-file t.txt --json   # re-parse saved model output, no API call
```

Rules the CLI keeps (tests enforce them, `test_agent_contract.py`):
- With `--json`, **stdout is exactly one JSON document**. Progress and errors are on stderr.
- It **never waits for input** unless stdin is a terminal and no input flag was given.
- Artifacts are always written. Their paths are in `artifacts` (`json_path`, `text_path`,
  `transcript_path`). Files are named `<source_id>.json|.txt|.transcript.txt` (a rerun adds `-2`). Default dir `~/.local/share/wtp/runs/`; `--session` defaults to `.../sessions/<session_id>/`;
  `--out-dir` overrides.

## Read the result in this order
1. **Exit code**, then `status` (per source; a session has `status_counts`):

   | code | status | meaning | what to do |
   |---|---|---|---|
   | 0 | ok | analyzed, every quote found | use it |
   | 1 | degraded | parse warnings, or a quote `not_found` | read `parse_warnings` / `evidence.items`; don't cite `not_found` quotes |
   | 2 | — | bad flags, missing key, unreadable file | read stderr; run `--check` |
   | 3 | transcript_failed | fetch failed or empty | read `error`; try another source or `--transcript-file` |
   | 4 | analysis_failed | model call raised | read `error`; retry later or switch provider |

   Multi-source runs exit with the worst code. One bad source doesn't stop the others.
2. **`evidence`**: `verified` (exact), `approximate` (≥80% of words in order: small edits),
   `stitched` (real sentences joined from different places; cite the pieces, not the whole),
   `not_found` (paraphrased or invented; never present as the speaker's words).
3. **`diagnostics.field_sources`**: `llm` = the model said it, `heuristic` = local guess,
   `default` = no information. Weigh accordingly.
4. **The signals**: `pass1`, `pass2`, `combined_summary`. Keys inside signal objects are the
   model's UPPERCASE labels (`QUOTE`, `CATEGORY`, ...).

## Models
Gemini, Claude (`anthropic`, default `claude-opus-5-5`, structured outputs + refusal fallback;
key optional after `ant auth login`; not yet run live), or any OpenAI-Chat-Completions server:
`LLM_PROVIDER` = gemini | anthropic | ollama | llamacpp | groq | openrouter | openai |
openai_compatible, plus `LLM_MODEL_NAME` (see `--describe` → environment).
For free, unlimited local runs: `LLM_PROVIDER=ollama LLM_MODEL_NAME=<from ollama list>`.
Check `run.structured_mode`: `json_object` means the server did not enforce the schema, so look
at `parse_warnings` for violations. Small local models produce valid JSON but invent quotes;
trust `evidence`, not the model.

## Cost and side effects
- A live run makes **one LLM call per source** (paid) and one YouTube fetch per URL.
  Transient failures are retried (`WTP_MAX_ATTEMPTS`, default 3, backoff from
  `WTP_RETRY_BASE_DELAY`=2 s), so a bad minute can mean up to 3 paid attempts per source.
  `run.attempts` records them. A 429 that survives all retries usually means quota: stop,
  don't loop. Gemini flash models returned 503 "high demand" for minutes at a time on 2026-10-14;
  if every attempt is 503, wait several minutes or set `GEMINI_MODEL_NAME` to another model.
  `--describe`, `--check`, `--replay` make no network calls.
- To test a parser or diagnostics change, **replay** a saved run instead of calling the model:
  `raw_output` is inside every result JSON, the transcript is beside it.
  ```bash
  jq -r .raw_output ~/.local/share/wtp/runs/<source_id>.json > /tmp/raw.txt
  wtp --replay /tmp/raw.txt --transcript-file ~/.local/share/wtp/runs/<source_id>.transcript.txt --json
  ```
- Never print or log the contents of `.env`. `--check` reports `api_key_present`, never the key.

## Measured behaviour (2026-10-14, this machine)
Three real Gemini runs (wedding-photography videos, 2026-08-17; model not recorded, `.env` then set
`gemini-3.6-flash`; new runs record it in `run.model`), re-checked by replay:
41 quotes → 28 verified, 6 approximate, 7 stitched, 0 not_found. So the model mostly quotes
faithfully but joins sentences ~17% of the time; `stitched` exists because of this.
Replay of one source: ~1.4 s wall. Quote check worst case: ~0.4 s for 35 fuzzy quotes on 53k chars.

## Change the code
```bash
uv run python -m unittest discover -s tests -t .    # 86 tests, ~15 s, no network
```
| file | role |
|---|---|
| `src/wtp/cli.py` | CLI: flags, input sources, exit codes, stdout/stderr discipline |
| `src/wtp/contract.py` | versions, exit codes, statuses, `--describe` document, domain glossary |
| `src/wtp/install.py` | config/data dirs, version, `--check-update`, `--self-update` |
| `prompt.py` | what the model should look for (format lives in the schema) |
| `model_output.py` | JSON Schema the provider enforces; JSON → internal signal dicts |
| `extract.py` | parser for pre-0.3 plain-text outputs, kept so old runs replay (`run.output_format`) |
| `retry.py` | transient vs permanent errors, exponential backoff |
| `diagnostics.py` | normalize vocabularies, heuristics, `field_sources` |
| `verify.py` | quote ↔ transcript matching (`evidence`) |
| `aggregate.py` | session rollups across sources |
| `render.py`, `session_store.py` | human report; artifact writing |
| `plugin/`, `.claude-plugin/` | Claude Code plugin + marketplace: the `wtp` skill (keep its version = package version; tested) |
| `providers/` | Gemini (`response_json_schema`), Claude (`claude.py`, `output_config.format`) and OpenAI Chat Completions (strict `json_schema`, falls back to `json_object`) adapters: `generate(prompt, system, schema) -> str`; presets in `main.PROVIDERS` |
| `tests/` | `test_main` (units), `test_agent_contract` (CLI contract, subprocess), `test_structured` (schema, retries) |

Invariants: keep stdout clean under `--json`; every failure becomes a result with a
`status`, never a traceback; bump `contract.SCHEMA_VERSION` (and `schemas.empty_result`)
on any breaking change to the JSON shape; add new top-level result fields to
`contract.FIELD_GUIDE` (a test fails otherwise); keep every schema object strict (all
properties required, `additionalProperties: false`), or OpenAI strict mode rejects it (tested).

## Known limits
- Quote matching is lexical: a faithful paraphrase is `not_found`.
- Sources run one at a time.
- No integration with Source Garden yet beyond the JSON fields meant for it.
