"""Check a memory store against the Vercy Governance Overlay.

This is the logic published at https://ver.cy/overlay/check.py, kept rule for rule,
with a structured report around it. A pass means one thing only: the overlay fields
are present and not empty. Values are not validated, and a pass does not mean that
a host enforces them. See ENFORCEMENT-CONTRACT.md for what enforcement means and how it is tested.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .profile import load_profile

LEVELS = {
    1: ["record_id", "valid_from", "valid_to"],
    2: ["source", "concept_owner", "conflict_policy"],
    3: ["release_to"],
}
SHOULD = ["owner_role", "supersedes"]
# required only on records that state a rule, and only where the store has such records
RULE_FIELDS = ["applies_to", "does_not_apply_to"]
# a record is taken to state a rule when it carries any of these
RULE_MARKERS = ["conflict_policy", "policy", "rule", "applies_to", "does_not_apply_to"]
# a record is taken to be restricted when it names an audience
RESTRICTED_MARKERS = ["release_to", "classification", "confidential", "restricted"]
# For these, an explicit null is a statement rather than a gap: a null valid_to means the
# record is still open, and a store that omits the key cannot say whether it knows.
NULLABLE = {"valid_to"}

SCOPE = "presence"
SCOPE_NOTE = ("A pass means the overlay fields are present and not empty. "
              "It does not check their values, and it does not mean that any host enforces them.")


class InputError(ValueError):
    """The store could not be read as records."""


def load_records(path: str | Path) -> list[dict[str, Any]]:
    """A JSON array, or one JSON object per line."""
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise InputError(f"{path} is not UTF-8 text") from exc
    return parse_records(text)


def parse_records(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    try:
        if text[0] == "[":
            records = json.loads(text)
        else:
            records = [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise InputError(f"not JSON or JSONL: line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise InputError("every record must be a JSON object")
    return records


def parse_map(spec: str | dict[str, str] | None) -> dict[str, str]:
    """`role=yourkey,role=yourkey`, or a ready mapping."""
    if isinstance(spec, dict):
        return {str(k): str(v) for k, v in spec.items()}
    out: dict[str, str] = {}
    for pair in (spec or "").split(","):
        if not pair.strip():
            continue
        role, _, key = pair.partition("=")
        out[role.strip()] = key.strip()
    return out


def present(record: dict, field: str, mapping: dict) -> bool:
    return mapping.get(field, field) in record


def get(record: dict, field: str, mapping: dict) -> Any:
    value = record.get(mapping.get(field, field))
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, (list, dict)) and not value:
        return None
    return value


def rid(record: dict, mapping: dict, index: int) -> str:
    return str(get(record, "record_id", mapping) or f"#{index}")


def states_a_rule(record: dict, mapping: dict) -> bool:
    return any(get(record, m, mapping) is not None for m in RULE_MARKERS)


def is_restricted(record: dict, mapping: dict) -> bool:
    return any(get(record, m, mapping) is not None for m in RESTRICTED_MARKERS)


def evaluate(records: list[dict], mapping: dict, policy_present: bool) -> tuple[int, list[tuple]]:
    """Returns (level reached, findings). A finding is (field, requirement, offenders)."""
    findings: list[tuple] = []
    reached = 0

    for level in (1, 2, 3):
        ok = True
        for field in LEVELS[level]:
            if field == "conflict_policy":
                # one policy per store, not one per record
                if not policy_present and not any(
                        get(r, "conflict_policy", mapping) for r in records):
                    findings.append((field, f"level {level} MUST",
                                     ["no conflict policy anywhere in the store"]))
                    ok = False
                continue
            if field == "release_to":
                restricted = [(i, r) for i, r in enumerate(records) if is_restricted(r, mapping)]
                if not restricted:
                    continue          # nothing restricted, the requirement is vacuous
                missing = [rid(r, mapping, i) for i, r in restricted
                           if get(r, "release_to", mapping) is None]
                if missing:
                    findings.append((field, f"level {level} MUST where restricted", missing))
                    ok = False
                continue
            if field in NULLABLE:
                missing = [rid(r, mapping, i) for i, r in enumerate(records)
                           if not present(r, field, mapping)]
                note = f"level {level} MUST be present, null means open"
            else:
                missing = [rid(r, mapping, i) for i, r in enumerate(records)
                           if get(r, field, mapping) is None]
                note = f"level {level} MUST"
            if missing:
                findings.append((field, note, missing))
                ok = False
        if not ok:
            break
        reached = level

    rules = [(i, r) for i, r in enumerate(records) if states_a_rule(r, mapping)]
    for field in RULE_FIELDS:
        missing = [rid(r, mapping, i) for i, r in rules if get(r, field, mapping) is None]
        if missing:
            findings.append((field, "MUST on any record that states a rule", missing))
            if reached >= 2:
                reached = 1

    for field in SHOULD:
        missing = [rid(r, mapping, i) for i, r in enumerate(records)
                   if get(r, field, mapping) is None]
        if missing:
            findings.append((field, "SHOULD", missing))
    return reached, findings


def check(records: Iterable[dict], mapping: str | dict | None = None,
          policy_present: bool = False, min_level: int = 1) -> dict[str, Any]:
    """The full report as a plain dict. Same logic for the CLI and the MCP tool."""
    records = list(records)
    mapping = parse_map(mapping)
    profile = load_profile()
    level, findings = evaluate(records, mapping, policy_present) if records else (0, [])
    return {
        "report": "vercy-check/1",
        "profile": profile["overlay"],
        "profile_version": profile["version"],
        "scope": SCOPE,
        "scope_note": SCOPE_NOTE,
        "records": len(records),
        "level": level,
        "min_level": min_level,
        "pass": bool(records) and level >= min_level,
        "mapping": mapping,
        "policy_outside_records": policy_present,
        "findings": [
            {"field": f, "requirement": req, "count": len(off), "offenders": off}
            for f, req, off in findings
        ],
    }


def format_text(report: dict[str, Any], quiet: bool = False) -> str:
    lines = [f"records: {report['records']}",
             f"level reached: {report['level']} of 3",
             f"profile: {report['profile']} {report['profile_version']}"]
    if not report["records"]:
        return "no records found"
    if not quiet:
        for item in report["findings"]:
            off = item["offenders"]
            shown = ", ".join(str(x) for x in off[:6])
            more = f" and {len(off) - 6} more" if len(off) > 6 else ""
            lines.append(f"  {item['field']:20} {item['requirement']:40} {shown}{more}")
    if report["level"] == 0:
        lines.append("")
        lines.append("Level 1 needs record_id, valid_from and valid_to on every record.")
    lines.append("")
    lines.append("scope: " + SCOPE_NOTE)
    return "\n".join(lines)
