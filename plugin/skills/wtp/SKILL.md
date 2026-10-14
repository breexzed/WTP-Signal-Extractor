---
name: wtp
description: Extract willingness-to-pay (WTP) and go-to-market signals from an interview, podcast or YouTube transcript with the `wtp` CLI, with every quote checked against the transcript. Use when the user wants to know whether customers would pay, what pain they already spend money on, which platforms or intermediaries gatekeep a market, or to analyze a YouTube video/transcript for buying signals.
---

# wtp: checked willingness-to-pay evidence

`wtp` asks an LLM for buying signals in a transcript, then checks the answer itself. You run it;
it never prompts when stdin isn't a terminal.

## 1. Preflight (no network, free)
```bash
command -v wtp || uv tool install git+https://github.com/breexzed/WTP-Signal-Extractor
wtp --check        # JSON; exit 2 = config problem, read config_error
wtp --describe     # the full contract: flags, exit codes, every field, domain glossary
```
If `--check` says no key: the user can add one to `~/.config/wtp/.env`, or run free and
local with `LLM_PROVIDER=ollama LLM_MODEL_NAME=<from ollama list>`. Never print `.env`.

## 2. Run (always with --json)
```bash
wtp --url "https://youtu.be/ID" --json                 # one video
wtp --transcript-file notes.txt --json                 # a file, or '-' for stdin
wtp --urls URL1 URL2 --json                            # several, plus a session rollup
wtp --session manifest.json --json                     # see `wtp --describe | jq .manifest_example`
```
stdout is one JSON document; progress is on stderr. Each live source costs one model call
(paid unless local), and transient errors retry up to 3 times. Ask before running more than a
handful of sources.

## 3. Read the result in this order
1. Exit code: 0 ok, 1 degraded, 2 usage/config, 3 transcript failed, 4 model failed.
2. `status`, then `error` if it failed.
3. `evidence`: `verified` / `approximate` quotes are the speaker's words. `stitched` quotes join
   real sentences from different places: cite the pieces. `not_found` quotes are unproven;
   never present them as something the speaker said.
4. `diagnostics.field_sources`: `llm` (model said it) outranks `heuristic` (local guess).
5. Then the signals: `pass1.behavior_signals` (money already spent, tools abandoned,
   workarounds) are strong; `opinion_signals` are weak. `pass2.gatekeeper_mentions` and
   `diagnostics.gatekeepers` name who controls access.

## 4. Report back
Lead with the strongest *verified* behavior signals and named gatekeepers, quote them
exactly, and say how many quotes were not found. Give the path in `artifacts.json_path`.
To re-check a saved run without paying again:
`wtp --replay RAW --transcript-file <artifacts.transcript_path> --json` (raw text is `raw_output`).
