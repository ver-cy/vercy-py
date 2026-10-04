"""Read-only Vercy MCP server over stdio (newline-delimited JSON-RPC 2.0).

Tools answer from the published corpus at https://ver.cy and from the bundled
Governance Overlay profile. Nothing is written anywhere; stdout carries protocol
messages only.
"""
from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from . import __version__
from .check import check, parse_records, InputError
from .corpus import Corpus, CorpusError
from .profile import overlay_profile

PROTOCOL = "2025-06-18"
SUPPORTED_PROTOCOLS = {"2025-06-18", "2025-03-26", "2024-11-05"}
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_models",
        "title": "Search Vercy models",
        "description": "Search the published Vercy model catalogue by name or need. Returns ranked "
                       "models with their ids, status and page URLs. Use resolve_model on a result "
                       "to read it.",
        "inputSchema": {"type": "object", "additionalProperties": False, "required": ["query"],
                        "properties": {"query": {"type": "string", "minLength": 1},
                                       "limit": {"type": "integer", "minimum": 1, "maximum": 25}}},
        "annotations": {**READ_ONLY, "openWorldHint": True},
    },
    {
        "name": "resolve_model",
        "title": "Resolve a Vercy model",
        "description": "Resolve a model by id, model id, slug or unique alias (for example "
                       "vr.wm-org-001 or WM-ORG-001). Returns metadata, relations and a citation; "
                       "with include_spec the specification text and whether its digest verified.",
        "inputSchema": {"type": "object", "additionalProperties": False, "required": ["id"],
                        "properties": {"id": {"type": "string", "minLength": 1},
                                       "include_spec": {"type": "boolean"}}},
        "annotations": {**READ_ONLY, "openWorldHint": True},
    },
    {
        "name": "get_overlay_profile",
        "title": "Get the Governance Overlay profile",
        "description": "The Vercy Governance Overlay: the fields a memory store needs for time, "
                       "authority and disclosure, their levels, definitions and measured effects.",
        "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
        "annotations": {**READ_ONLY, "openWorldHint": False},
    },
    {
        "name": "check_record",
        "title": "Check records against the overlay",
        "description": "Check one record or a list of records against the Governance Overlay and "
                       "return the level reached and the missing fields. Same logic as the "
                       "`vercy check` CLI. A pass means structure and presence only, not enforcement.",
        "inputSchema": {"type": "object", "additionalProperties": False, "required": ["records"],
                        "properties": {
                            "records": {"description": "A record object, a list of record objects, "
                                                       "or JSON / JSONL text.",
                                        "type": ["object", "array", "string"]},
                            "map": {"description": "Your field names, as {overlay_field: your_key}.",
                                    "type": "object", "additionalProperties": {"type": "string"}},
                            "policy_outside_records": {"type": "boolean"},
                            "min_level": {"type": "integer", "minimum": 1, "maximum": 3}}},
        "annotations": {**READ_ONLY, "openWorldHint": False},
    },
    {
        "name": "cite",
        "title": "Cite a Vercy model",
        "description": "Return the citation for a model: text, page URL, specification URL, "
                       "version and digest. Use it for anything you answered from Vercy.",
        "inputSchema": {"type": "object", "additionalProperties": False, "required": ["id"],
                        "properties": {"id": {"type": "string", "minLength": 1}}},
        "annotations": {**READ_ONLY, "openWorldHint": True},
    },
]


def _validate(arguments: dict[str, Any], schema: dict[str, Any]) -> None:
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in arguments:
            raise CorpusError("invalid_argument", f"missing required argument {key!r}")
    for key, value in arguments.items():
        if key not in props:
            raise CorpusError("invalid_argument", f"unknown argument {key!r}")
        expected = props[key].get("type")
        types = expected if isinstance(expected, list) else [expected] if expected else []
        pytypes = {"string": str, "integer": int, "boolean": bool, "object": dict, "array": list}
        if types and not any(isinstance(value, pytypes[t]) and not (t == "integer" and isinstance(value, bool))
                             for t in types):
            raise CorpusError("invalid_argument", f"{key!r} must be {' or '.join(types)}")


def _records(value: Any) -> list[dict]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        if not all(isinstance(r, dict) for r in value):
            raise CorpusError("invalid_argument", "every record must be an object")
        return value
    try:
        return parse_records(str(value))
    except InputError as exc:
        raise CorpusError("invalid_argument", str(exc)) from exc


class Server:
    def __init__(self, corpus: Corpus | None = None):
        self.corpus = corpus or Corpus()

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = next((t for t in TOOLS if t["name"] == name), None)
        if tool is None:
            raise CorpusError("unknown_tool", f"unknown tool {name!r}")
        _validate(arguments, tool["inputSchema"])
        if name == "search_models":
            return self.corpus.search(arguments["query"], arguments.get("limit", 8))
        if name == "resolve_model":
            return self.corpus.resolve(arguments["id"], bool(arguments.get("include_spec")))
        if name == "get_overlay_profile":
            return overlay_profile()
        if name == "check_record":
            return check(_records(arguments["records"]), arguments.get("map") or {},
                         bool(arguments.get("policy_outside_records")),
                         int(arguments.get("min_level", 1)))
        return self.corpus.cite(arguments["id"])

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method")
        if request_id is None:          # a notification, nothing to answer
            return None
        if method == "initialize":
            asked = (request.get("params") or {}).get("protocolVersion")
            version = asked if asked in SUPPORTED_PROTOCOLS else PROTOCOL
            return _result(request_id, {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "vercy", "title": "Vercy", "version": __version__},
                "instructions": "Read-only access to the Vercy model catalogue and the Governance "
                                "Overlay. Cite what you use with the cite tool.",
            })
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(request_id, {"tools": TOOLS})
        if method == "tools/call":
            params = request.get("params") or {}
            arguments = params.get("arguments") or {}
            if not isinstance(params, dict) or not isinstance(arguments, dict):
                return _error(request_id, -32602, "invalid tools/call parameters")
            try:
                payload = self.call(str(params.get("name")), arguments)
                is_error = False
            except CorpusError as exc:
                payload, is_error = exc.as_dict(), True
            return _result(request_id, {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=1)}],
                "structuredContent": payload,
                "isError": is_error,
            })
        return _error(request_id, -32601, f"method not found: {method}")


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(stdin: TextIO | None = None, stdout: TextIO | None = None, server: Server | None = None) -> int:
    if stdin is None or stdout is None:
        # MCP stdio is UTF-8 by specification; Windows consoles default to a code page.
        for stream in (sys.stdin, sys.stdout):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
        stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    server = server or Server()
    for line in stdin:
        if not line.strip():
            continue
        try:
            response = server.handle(json.loads(line))
        except Exception as exc:  # protocol boundary: answer with an error, never crash
            response = _error(None, -32700, f"invalid request: {exc}")
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0
