# Changelog

All notable changes. Versions are git tags; each one has a [GitHub Release](https://github.com/breexzed/WTP-Signal-Extractor/releases).

## 0.6.2 — 2026-10-15
From two outside reviews:
- Python 3.11+ (was 3.14+). All tests pass on 3.11; CI now runs 3.11 and 3.14.
- README explains the FGP framework (phases 0–3.5, gatekeeper Type1–4, registers) and says
  plainly that outputs are hypotheses to confirm with real conversations or pre-sales.

## 0.6.1 — 2026-10-14
- Failed runs show only what failed and a wtp-specific `next_step` (new result field), instead of an empty report and the library's error text twice. The full error stays in `error`; it is no longer copied into `parse_warnings`.
- `WTP_YT_PROXY` routes YouTube caption fetches through a proxy, the documented way around IP blocks. `wtp --check` reports `youtube_proxy_set`, never the URL.
- Found by installing and running v0.6.0: YouTube answered `RequestBlocked` after ~8 caption fetches in a day.

## 0.6.0 — 2026-10-14
- **Claude as the model:** `LLM_PROVIDER=anthropic` (default `claude-opus-5-5`) with schema-enforced structured outputs, streaming, and server-side refusal fallback. Not yet run against the live API.
- **Claude Code plugin:** `/plugin install wtp --marketplace breexzed/WTP-Signal-Extractor` adds a `wtp` skill so Claude Code can run the CLI and read its evidence correctly.
- **Clean file names:** runs are saved as `<source_id>.json` / `.txt` / `.transcript.txt` (no repeated timestamps); a rerun gets `-2` instead of overwriting.
- MIT license, contributing guide, security policy, issue/PR templates, package metadata, ruff in CI.

## 0.5.1 — 2026-10-14
- Missing-key error names the exact file to edit (`~/.config/wtp/.env`) and the no-key local option.
- Single-source runs are named after the source, like batch runs.

## 0.5.0 — 2026-10-14
- Installable `wtp` command (`uv tool install git+…@vX.Y.Z`); config in `~/.config/wtp/`, runs in `~/.local/share/wtp/`.
- `--version`, `--check-update`, `--self-update`. CI on every push; releases on `v*` tags.

## 0.4.0 — 2026-10-14
- Provider presets: gemini, ollama, llamacpp, groq, openrouter, openai, openai_compatible.
- OpenAI-compatible adapter moved to Chat Completions (Ollama has no Responses API); falls back to `json_object` and validates the schema locally.

## 0.3.0 — 2026-10-14
- Agent-first CLI: `--json`, exit codes, `--describe`, `--check`, `--replay`, no prompts without a TTY.
- Model output is schema-enforced JSON instead of regex-parsed text; retries with backoff.
- Every quote graded against the transcript (`verified` / `approximate` / `stitched` / `not_found`); diagnostics labelled `llm` vs `heuristic`.

## Before 0.3.0 — 2026-04 to 2026-05
- Interactive CLI, Gemini text output parsed with regex, batch and session-manifest runs, Source Garden diagnostics.
