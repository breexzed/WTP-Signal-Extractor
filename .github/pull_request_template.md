## What and why

## How I verified it
- [ ] `uv run python -m unittest discover -s tests -t .`
- [ ] `uvx ruff@0.12.0 check src tests`
- [ ] If the JSON shape changed: `SCHEMA_VERSION` bumped and `contract.FIELD_GUIDE` updated
- [ ] CHANGELOG entry (user-visible changes)
