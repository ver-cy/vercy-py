# vercy

Two tools for agent memory, in one package with no dependencies.

- `vercy check` - checks a memory store against the [Vercy Governance Overlay](https://ver.cy/overlay/):
  the fields a store needs to answer questions about time, authority and disclosure.
- `vercy mcp` - a read-only MCP server over the published Vercy model catalogue.

Apache-2.0. No telemetry. The checker makes no network calls. The MCP server only reads `https://ver.cy`.

## Check a store

```bash
uvx vercy check memory.jsonl
```

Input is a JSON array, or one JSON object per line. Your field names can stay your own:

```bash
uvx vercy check graph.jsonl --map record_id=uuid,valid_from=valid_at,valid_to=invalid_at,source=episode
```

```
records: 30
level reached: 1 of 3
profile: vercy-governance-overlay 1.0
  concept_owner        level 2 MUST                             D-101, D-102, D-103, D-201, D-202, D-301 and 24 more
  conflict_policy      level 2 MUST                             no conflict policy anywhere in the store
```

| Level | Fields | What it unlocks |
|---|---|---|
| 1 | `record_id`, `valid_from`, `valid_to` | Answers about any date; an update can name what it replaces |
| 2 | `source`, `concept_owner`, `conflict_policy` | Disagreement resolved by rule, change requests routed to an owner |
| 3 | `release_to` where a record is restricted | What may cross a boundary, without leaking or over-refusing |

Options: `--json` for a machine report, `--min-level 2` to raise the bar, `--policy` when the conflict
policy lives outside the records. Exit codes: `0` the store reaches the level, `1` it does not,
`2` the input could not be read. That makes it a CI gate.

**What a pass means.** The records carry the fields in the required shape. Nothing more. It does not
mean a host enforces them: a record can carry `release_to` while another retrieval path ignores it.
Enforcement is a separate, testable claim, defined in [ENFORCEMENT-CONTRACT.md](ENFORCEMENT-CONTRACT.md).

## Use Vercy from an agent

```bash
claude mcp add vercy -- uvx vercy mcp
```

Or in any MCP client configuration:

```json
{ "mcpServers": { "vercy": { "command": "uvx", "args": ["vercy", "mcp"] } } }
```

| Tool | What it returns |
|---|---|
| `search_models` | Ranked models for a name or need |
| `resolve_model` | One model by id, model id, slug or unique alias; with `include_spec`, the specification and whether its sha256 digest verified |
| `get_overlay_profile` | The overlay fields, levels, definitions and measured effects |
| `check_record` | The `vercy check` report for one record or many, same code path as the CLI |
| `cite` | Citation text, page URL, specification URL, version and digest |

All tools are read-only. Errors come back as `{"error": code, "message": ...}` with codes an agent can
branch on: `unknown_model`, `not_published`, `ambiguous_id`, `invalid_argument`, `upstream_unreachable`.

## Why these fields

Each field is in the profile because a published benchmark measured what changes without it. On the
collaborative-memory benchmark, a bitemporal graph without owner, conflict rule or release list scored
77.4 percent; the same knowledge with the overlay scored 93.5 to 96.8 percent across three store shapes.
Methods, raw runs and harnesses: [ver.cy/benchmarks/collaborative-memory-v1](https://ver.cy/benchmarks/collaborative-memory-v1/).

## Development

```bash
python -m unittest discover -s tests
```

`src/vercy/data/profile.json` is generated from `profile.yaml` (the file published at
`https://ver.cy/overlay/profile.yaml`) by `python tools/sync_profile.py`.
