"""Offline tests. Run: python -m unittest discover -s tests"""
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vercy.check import check, load_records  # noqa: E402
from vercy.cli import main  # noqa: E402
from vercy.corpus import Corpus, CorpusError  # noqa: E402
from vercy.mcp import Server, serve  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
GRAPH_MAP = "record_id=uuid,valid_from=valid_at,valid_to=invalid_at,source=episode"

SPEC = b"name: Organization\nversion: 0.3.0\n"
INDEX = {"models": [
    {"id": "vr.wm-org-001", "modelId": "WM-ORG-001", "slug": "wm-org-001-organization",
     "name": "Organization", "version": "0.3.0", "status": "published", "installable": True,
     "aliases": ["Organisation", "Shared"], "specUrl": "https://ver.cy/models/wm-org-001-organization/spec.yaml",
     "pageUrl": "https://ver.cy/models/wm-org-001-organization/",
     "digest": "sha256:" + hashlib.sha256(SPEC).hexdigest()},
    {"id": "vr.wm-org-009", "modelId": "WM-ORG-009", "slug": "wm-org-009-guild", "name": "Guild",
     "version": "0.1.0", "status": "published", "aliases": ["Shared"],
     "specUrl": "https://ver.cy/models/wm-org-009-guild/spec.yaml",
     "pageUrl": "https://ver.cy/models/wm-org-009-guild/", "digest": "sha256:00"},
    {"id": "vr.wm-act-022", "modelId": "WM-ACT-022", "slug": "wm-act-022-experiment-trial",
     "name": "Experiment Trial", "status": "todo"},
]}
SEARCH = {"matches": [
    {"id": "vr.wm-org-001", "name": "Organization", "status": "published"},
    {"id": "vr.wm-act-022", "name": "Experiment Trial", "status": "todo"},
]}


def fake_fetch(url):
    if url.endswith("/models/runtime-index.json"):
        return json.dumps(INDEX).encode()
    if "/api/v1/models/search/" in url:
        return json.dumps(SEARCH).encode()
    if url.endswith("wm-org-001-organization/spec.yaml"):
        return SPEC
    if url.endswith("wm-org-009-guild/spec.yaml"):
        return b"tampered"
    raise CorpusError("upstream_http_error", f"{url} answered 404")


def run_cli(*args):
    out = io.StringIO()
    old = sys.stdout
    sys.stdout = out
    try:
        code = main(list(args))
    finally:
        sys.stdout = old
    return code, out.getvalue()


class CheckerParity(unittest.TestCase):
    """Same verdicts as the checker published at ver.cy/overlay/check.py."""

    def test_fixture_levels(self):
        self.assertEqual(check(load_records(FIX / "fixture-overlay.jsonl"))["level"], 3)
        self.assertEqual(check(load_records(FIX / "fixture-flat.jsonl"))["level"], 0)
        self.assertEqual(check(load_records(FIX / "fixture-graph.jsonl"))["level"], 0)

    def test_aliases_lift_a_foreign_store(self):
        report = check(load_records(FIX / "fixture-graph.jsonl"), GRAPH_MAP)
        self.assertEqual(report["level"], 1)
        missing = {f["field"] for f in report["findings"]}
        self.assertIn("concept_owner", missing)
        self.assertNotIn("source", missing)   # mapped to episode

    def test_null_valid_to_is_a_statement_but_absence_is_not(self):
        base = {"record_id": "a", "valid_from": "2026-01-01"}
        self.assertEqual(check([{**base, "valid_to": None}])["level"], 1)
        report = check([base])
        self.assertEqual(report["level"], 0)
        self.assertEqual(report["findings"][0]["offenders"], ["a"])

    def test_restriction_requires_release_to(self):
        recs = [{"record_id": "a", "valid_from": "2026-01-01", "valid_to": None, "source": "s",
                 "concept_owner": "o", "conflict_policy": "newest-wins", "applies_to": "x",
                 "does_not_apply_to": "y", "classification": "internal"}]
        self.assertEqual(check(recs)["level"], 2)
        recs[0]["release_to"] = ["finance"]
        self.assertEqual(check(recs)["level"], 3)

    def test_report_states_its_scope(self):
        report = check(load_records(FIX / "fixture-overlay.jsonl"))
        self.assertEqual(report["scope"], "structure-and-presence")
        self.assertEqual(report["profile_version"], "1.0")


class Cli(unittest.TestCase):
    def test_exit_codes(self):
        self.assertEqual(run_cli("check", str(FIX / "fixture-overlay.jsonl"))[0], 0)
        self.assertEqual(run_cli("check", str(FIX / "fixture-flat.jsonl"))[0], 1)
        self.assertEqual(run_cli("check", str(FIX / "fixture-graph.jsonl"), "--map", GRAPH_MAP)[0], 0)
        self.assertEqual(run_cli("check", str(FIX / "fixture-graph.jsonl"), "--map", GRAPH_MAP,
                                 "--min-level", "2")[0], 1)

    def test_unreadable_input_is_exit_2(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write("{not json\n")
        old = sys.stderr
        sys.stderr = io.StringIO()
        try:
            self.assertEqual(run_cli("check", f.name)[0], 2)
            self.assertEqual(run_cli("check", f.name + ".missing")[0], 2)
        finally:
            sys.stderr = old

    def test_json_report_names_the_failing_record(self):
        code, out = run_cli("check", str(FIX / "fixture-graph.jsonl"), "--map", GRAPH_MAP, "--json")
        report = json.loads(out)
        owner = next(f for f in report["findings"] if f["field"] == "concept_owner")
        self.assertIn("D-101", owner["offenders"])
        self.assertEqual(owner["count"], 30)

    def test_module_entry_point(self):
        result = subprocess.run([sys.executable, "-m", "vercy", "version"], capture_output=True,
                                text=True, cwd=ROOT / "src")
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout.strip(), r"^\d+\.\d+\.\d+$")


class Mcp(unittest.TestCase):
    def setUp(self):
        self.server = Server(Corpus(fetch=fake_fetch, base="https://ver.cy"))

    def rpc(self, method, params=None, rid=1):
        return self.server.handle({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})

    def tool(self, name, **arguments):
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})["result"]
        return result["isError"], result["structuredContent"]

    def test_handshake_and_tools(self):
        init = self.rpc("initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(init["protocolVersion"], "2025-06-18")
        names = {t["name"] for t in self.rpc("tools/list")["result"]["tools"]}
        self.assertEqual(names, {"search_models", "resolve_model", "get_overlay_profile", "check_record", "cite"})
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in self.rpc("tools/list")["result"]["tools"]))
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_search_resolve_cite(self):
        err, found = self.tool("search_models", query="organization")
        self.assertFalse(err)
        self.assertEqual([m["id"] for m in found["matches"]], ["vr.wm-org-001"])  # todo hidden
        err, model = self.tool("resolve_model", id="WM-ORG-001", include_spec=True)
        self.assertFalse(err)
        self.assertTrue(model["digest_verified"])
        err, cite = self.tool("cite", id=found["matches"][0]["id"])
        self.assertEqual(cite["url"], model["page_url"])
        self.assertEqual(cite["version"], model["version"])

    def test_tampered_spec_is_reported_not_hidden(self):
        err, model = self.tool("resolve_model", id="vr.wm-org-009", include_spec=True)
        self.assertFalse(err)
        self.assertFalse(model["digest_verified"])

    def test_structured_errors(self):
        self.assertEqual(self.tool("resolve_model", id="vr.nope")[1]["error"], "unknown_model")
        self.assertEqual(self.tool("resolve_model", id="WM-ACT-022")[1]["error"], "not_published")
        self.assertEqual(self.tool("resolve_model", id="Shared")[1]["error"], "ambiguous_id")
        self.assertEqual(self.tool("resolve_model")[1]["error"], "invalid_argument")
        self.assertEqual(self.tool("resolve_model", id="x", extra=1)[1]["error"], "invalid_argument")
        self.assertEqual(self.tool("nope")[1]["error"], "unknown_tool")
        self.assertEqual(self.rpc("nope")["error"]["code"], -32601)

    def test_check_record_agrees_with_cli(self):
        text = (FIX / "fixture-graph.jsonl").read_text(encoding="utf-8")
        mapping = dict(p.split("=") for p in GRAPH_MAP.split(","))
        err, via_mcp = self.tool("check_record", records=text, map=mapping)
        _, out = run_cli("check", str(FIX / "fixture-graph.jsonl"), "--map", GRAPH_MAP, "--json")
        via_cli = json.loads(out)
        for key in ("level", "pass", "findings", "profile_version"):
            self.assertEqual(via_mcp[key], via_cli[key], key)

    def test_profile(self):
        err, profile = self.tool("get_overlay_profile")
        self.assertEqual(len(profile["fields"]), 12)
        self.assertEqual(profile["source_url"], "https://ver.cy/overlay/profile.yaml")

    def test_stdio_framing(self):
        lines = "\n".join(json.dumps(m) for m in [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]) + "\nnot json\n"
        out = io.StringIO()
        serve(io.StringIO(lines), out, self.server)
        replies = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual([r.get("id") for r in replies], [1, 2, None])
        self.assertEqual(replies[2]["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
