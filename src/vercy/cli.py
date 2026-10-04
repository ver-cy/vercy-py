"""`vercy` command line.

    vercy check store.jsonl [--map role=key,...] [--policy] [--min-level N] [--json]
    vercy mcp
    vercy profile
    vercy version

Exit codes for `check`: 0 the store reaches --min-level (default 1), 1 it does not,
2 the input could not be read.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .check import InputError, check, format_text, load_records
from .profile import overlay_profile


def _check(args: argparse.Namespace) -> int:
    try:
        records = load_records(args.store)
    except InputError as exc:
        print(f"vercy check: {exc}", file=sys.stderr)
        return 2
    report = check(records, args.map, args.policy, args.min_level)
    report["store"] = args.store
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(format_text(report, args.quiet))
    return 0 if report["pass"] else 1


def _mcp(_: argparse.Namespace) -> int:
    from .mcp import serve
    return serve()


def _profile(_: argparse.Namespace) -> int:
    print(json.dumps(overlay_profile(), ensure_ascii=False, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vercy", description="Vercy: governed structure for agent memory.")
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="check a store against the Governance Overlay")
    c.add_argument("store", help="JSON array or JSONL file, one record per object")
    c.add_argument("--map", default="", help="your field names: role=yourkey,role=yourkey")
    c.add_argument("--policy", action="store_true", help="the conflict policy is configured outside the records")
    c.add_argument("--min-level", type=int, choices=(1, 2, 3), default=1, help="level needed to pass (default 1)")
    c.add_argument("--json", action="store_true", help="print the machine-readable report")
    c.add_argument("--quiet", action="store_true", help="omit the per-field findings")
    c.set_defaults(func=_check)

    m = sub.add_parser("mcp", help="run the read-only MCP server on stdio")
    m.set_defaults(func=_mcp)

    p = sub.add_parser("profile", help="print the bundled Governance Overlay profile")
    p.set_defaults(func=_profile)

    v = sub.add_parser("version", help="print the version")
    v.set_defaults(func=lambda _: print(__version__) or 0)

    args = parser.parse_args(argv)
    if args.command != "mcp" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # reports carry record ids in any script
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
