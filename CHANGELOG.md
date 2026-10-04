# Changelog

## Unreleased

- `ENFORCEMENT-CONTRACT.md` draft 0.4: immutable records, host attestation, fail closed on
  unverifiable records, decide over every record of a concept; two more fixture cases.

## 0.1.0 - 2026-10-04

- `vercy check`: the Governance Overlay checker from ver.cy/overlay/check.py, rule for rule, with a
  JSON report, `--min-level`, and exit code 2 for unreadable input.
- `vercy mcp`: read-only stdio MCP server with `search_models`, `resolve_model`, `get_overlay_profile`,
  `check_record` and `cite`. Specification digests are verified on `include_spec`.
- `ENFORCEMENT-CONTRACT.md`: draft 0.3 of what enforcing the overlay means and how it is tested.
