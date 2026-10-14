# Security policy

## Reporting a vulnerability
Please report security issues privately through
[GitHub private vulnerability reporting](https://github.com/breexzed/WTP-Signal-Extractor/security/advisories/new),
not in a public issue. Expect a first reply within a week.

## What wtp handles
- **API keys** are read from the environment, `./.env` or `~/.config/wtp/.env`. They are sent
  only to the model provider you configure. `wtp --check` reports whether a key is present,
  never its value.
- **Transcripts** are sent to that provider, and saved locally under `~/.local/share/wtp/`.
  With `LLM_PROVIDER=ollama` or `llamacpp`, nothing leaves your machine except YouTube fetches.
- **Updates:** `--check-update` asks the GitHub API for the latest release; `--self-update`
  reinstalls that tag from this repository with `uv`.

## Supported versions
Only the latest release receives fixes.
