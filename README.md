# wtp

wtp is an open-source, agent-first CLI that reads an interview, podcast or YouTube transcript and
tells you whether people would actually **pay**: the money they already spend, the tools they
dropped, the workarounds they live with, and who controls their market. An LLM finds the signals;
wtp then checks every quote against the transcript, so you know which evidence is real. Built for
AI agents to run unattended, which is why it's pleasant for people too.

## Current release

- **[v0.6.0 Alpha →](https://github.com/breexzed/WTP-Signal-Extractor/releases/latest)**: Linux (tested in CI on every release); macOS should work but is untested. Python 3.14, which uv installs for you.
  ```bash
  uv tool install git+https://github.com/breexzed/WTP-Signal-Extractor@v0.6.0
  ```
- **Claude Code plugin**: lets Claude Code run wtp and read its evidence correctly.
  ```
  /plugin install wtp --marketplace breexzed/WTP-Signal-Extractor
  ```

This is pre-release software. Expect fast releases and changing output fields: check
`schema_version` before you depend on one. GitHub Releases only for now; PyPI comes later.

## Why wtp

Customers say they want many things and pay for few. The tell is behavior, not opinion, and it
sits buried in hours of interviews. Reading them by hand doesn't scale, and an LLM summary can't
be trusted: models paraphrase, stitch sentences together, and occasionally invent quotes. wtp
aims for the third option: let the model read everything, then **check its work** before you
believe it.

- **Behavior over opinion.** Money spent, tools abandoned, active workarounds and "it cost us a
  client" are strong evidence; wishes and hypotheticals are kept separate as weak evidence.
- **Every quote is checked.** Each quote is graded against the transcript: `verified` (exact),
  `approximate` (small edits), `stitched` (real sentences joined from different places) or
  `not_found` (unproven). Any `not_found` marks the run `degraded`.
- **Go-to-market map, not just a summary.** Cascades that hurt the operator's own customers,
  gatekeepers they can't bypass (platforms, distributors, certifiers), what those gatekeepers
  protect, and how the niche describes itself.
- **Any model, including free local ones.** Gemini, Claude, OpenAI, Groq, OpenRouter, or local
  Ollama and llama.cpp. The model must return JSON that matches wtp's schema, enforced by the
  provider where it can be and checked locally always.
- **No context left behind.** One JSON document on stdout, logs on stderr, exit codes that mean
  something, `wtp --describe` for the whole contract, and labels saying which judgments came from
  the model and which from a heuristic. An agent never has to read the source to use it.
- **Fails loudly, retries sensibly.** Rate limits, 5xx errors, timeouts and malformed replies are
  retried with backoff; bad keys, missing captions and refusals fail at once with the next step
  in the error.
- **Updates itself.** `wtp --check-update` compares with the latest release; `wtp --self-update`
  installs it.

```console
$ wtp --replay raw.txt --transcript-file transcript.txt --json \
    | jq -c '{status, evidence: .evidence | {total, verified, approximate, stitched, not_found}}'
{"status":"ok","evidence":{"total":13,"verified":10,"approximate":1,"stitched":2,"not_found":0}}
```
<sub>Real output: a saved Gemini analysis of a wedding-industry video, re-checked offline against its transcript.</sub>

## How it works

- **One model call per source.** YouTube captions (or your text) go to the model with
  `prompt.py` (what to look for) and `model_output.py` (the JSON Schema it must follow).
- **Local checks, no model.** `verify.py` grades quotes, `diagnostics.py` normalizes values and
  fills gaps with labelled heuristics, `aggregate.py` rolls many sources into one session report.
- **Plain files.** Each source saves `<source_id>.json`, a readable `.txt` report and the
  `.transcript.txt` under `~/.local/share/wtp/`, so any run can be re-checked offline with
  `--replay`.
- **Python, standard library plus provider SDKs.** No database, no server.

Measured on 2026-10-14: three Gemini analyses replayed against their transcripts gave 41 quotes:
28 verified, 6 approximate, 7 stitched, 0 invented. A tiny local model (`qwen2.5:0.5b`) returned
schema-valid JSON on the first try but invented most of its quotes, and wtp flagged the run.

## Open source & cost

wtp is free software under the [MIT license](LICENSE). It never ships or holds a key of its own:
you bring your model. Local models (Ollama, llama.cpp) cost nothing and keep transcripts on your
machine; hosted ones bill you per call. Set the provider in `~/.config/wtp/.env`:

```bash
LLM_PROVIDER=ollama          LLM_MODEL_NAME=qwen2.5:7b        # free, local
LLM_PROVIDER=gemini          GEMINI_API_KEY=...               # free tier, rate limited
LLM_PROVIDER=anthropic       ANTHROPIC_API_KEY=...            # Claude (default claude-opus-5-5)
LLM_PROVIDER=openai_compatible  LLM_BASE_URL=...  LLM_MODEL_NAME=...   # any Chat Completions server
```
`wtp --check` shows what is configured (never the key), and `wtp --describe` lists every option.
The Claude adapter is covered by tests but has not yet been run against the live API.

## Use

```bash
wtp --check                                     # config and paths, no network
wtp --url "https://youtu.be/VIDEO_ID"           # readable report
wtp --transcript-file interview.txt --json      # JSON on stdout ('-' reads stdin)
wtp --session manifest.json --json              # many sources + a session rollup
```
Exit codes: `0` ok, `1` degraded, `2` usage or config, `3` transcript failed, `4` model failed.
[AGENTS.md](AGENTS.md) explains how to read a result field by field.

## Build from source

Prerequisite: [uv](https://docs.astral.sh/uv/). It installs the pinned Python and locked dependencies.

```bash
git clone https://github.com/breexzed/WTP-Signal-Extractor && cd WTP-Signal-Extractor
uv sync
uv run wtp --describe | head
```

## Development & verification

[AGENTS.md](AGENTS.md) is the contributor guide for people and AI agents: the CLI contract, the
invariants, and where each piece lives. The short loop:

```bash
uv run python -m unittest discover -s tests -t .   # 86 tests, no network, no API key
uvx ruff@0.12.0 check src tests
```

CI runs both on every push. A `v*` tag runs them again, builds the wheel, installs it the way a
user would, and publishes the GitHub Release; it refuses a tag that doesn't match the package
version.

## Contributing

wtp is in Alpha. Bug reports with the command, its exit code and `wtp --check` output are very
welcome: use the issue forms, and never attach API keys, `.env` files or transcripts you can't
share. For larger changes (a new provider, a new output field, prompt or schema changes), open an
issue first so we agree on the shape before you invest in a pull request. See
[CONTRIBUTING.md](CONTRIBUTING.md) and, for vulnerabilities, [SECURITY.md](SECURITY.md).
