# Contributing

Thanks for helping. Bug reports with a way to reproduce them are the most useful thing you can send.

## Before you start
- **Small fixes:** open a pull request.
- **Larger changes** (a new provider, a new output field, a change to the prompt or schema):
  open an issue first so we agree on the shape before you invest in it.
- Read [AGENTS.md](AGENTS.md). It is the contributor guide for people and AI agents alike:
  the CLI contract, the invariants, and where each piece lives.

## Set up and verify
```bash
git clone https://github.com/breexzed/WTP-Signal-Extractor && cd WTP-Signal-Extractor
uv sync
uv run python -m unittest discover -s tests -t .   # no network, no API key needed
uvx ruff@0.12.0 check src tests
uv run wtp --describe | head
```
CI runs the same steps on every push and pull request.

## Rules that keep the tool trustworthy
- With `--json`, stdout holds exactly one JSON document. Logs go to stderr.
- Every failure becomes a result with a `status`, never a traceback.
- A change to the JSON shape bumps `SCHEMA_VERSION` and documents the field in `contract.FIELD_GUIDE`.
- Every schema object stays strict (all properties required, `additionalProperties: false`).
- Tests never call a real model or YouTube. Mock them, or use `--replay`.

## Bug reports
Use the bug report form. Include `wtp --version`, `wtp --check` (it never prints keys), the
command you ran and its exit code. **Never paste API keys, `.env` files, or transcripts you
don't have the right to share.**

## Releases (maintainer)
Bump `version` in `pyproject.toml` and `plugin/.claude-plugin/plugin.json`, add a CHANGELOG
entry, commit, then `git tag vX.Y.Z && git push origin vX.Y.Z`. The release workflow refuses a
tag that doesn't match the package version.
