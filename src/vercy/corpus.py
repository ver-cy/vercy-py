"""Read-only access to the published Vercy corpus at https://ver.cy.

Only GET requests to the configured base URL. No credentials, no telemetry, no
writes. The base URL can be changed with VERCY_BASE_URL (for a mirror or a test).
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from . import __version__

# Statuses the site does not show (owner decision 2026-10-04, models/visibility.php).
HIDDEN_STATUSES = {"todo"}
MAX_SPEC_BYTES = 512 * 1024

Fetcher = Callable[[str], bytes]


class CorpusError(Exception):
    """A structured, user-facing failure: a code an agent can branch on, and a message."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message}


def base_url() -> str:
    return os.environ.get("VERCY_BASE_URL", "https://ver.cy").rstrip("/")


def http_get(url: str, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": f"vercy-py/{__version__}",
        "Accept": "application/json, text/plain, */*",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(MAX_SPEC_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise CorpusError("upstream_http_error", f"{url} answered {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CorpusError("upstream_unreachable", f"{url} could not be reached: {exc}") from exc


class Corpus:
    def __init__(self, fetch: Fetcher | None = None, base: str | None = None):
        self.fetch = fetch or http_get
        self.base = (base or base_url()).rstrip("/")
        self._index: dict[str, Any] | None = None

    def _json(self, path: str) -> Any:
        raw = self.fetch(self.base + path)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CorpusError("upstream_invalid", f"{path} did not return JSON") from exc

    def runtime_index(self) -> dict[str, Any]:
        if self._index is None:
            self._index = self._json("/models/runtime-index.json")
        return self._index

    def search(self, query: str, limit: int = 8) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise CorpusError("invalid_argument", "query must not be empty")
        params = urllib.parse.urlencode({"q": query, "limit": max(1, min(25, int(limit)))})
        result = self._json(f"/api/v1/models/search/?{params}")
        matches = [m for m in result.get("matches", []) if m.get("status") not in HIDDEN_STATUSES]
        return {"query": query, "count": len(matches), "matches": matches,
                "source": f"{self.base}/api/v1/models/search/?{params}"}

    def find(self, identifier: str) -> dict[str, Any]:
        """An exact match on id, model id, slug, page URL or alias. Case-insensitive."""
        wanted = identifier.strip().lower().rstrip("/")
        if not wanted:
            raise CorpusError("invalid_argument", "id must not be empty")
        exact, by_alias = None, []
        for model in self.runtime_index().get("models", []):
            keys = {str(model.get(k, "")).lower() for k in ("id", "modelId", "slug")}
            keys.add(str(model.get("pageUrl", "")).lower().rstrip("/"))
            if wanted in keys:
                exact = model
                break
            if wanted in {str(a).lower() for a in model.get("aliases", [])}:
                by_alias.append(model)
        model = exact or (by_alias[0] if len(by_alias) == 1 else None)
        if model is None and len(by_alias) > 1:
            names = ", ".join(sorted(str(m.get("id")) for m in by_alias)[:10])
            raise CorpusError("ambiguous_id", f"{identifier!r} is an alias of several models: {names}")
        if model is None:
            raise CorpusError("unknown_model",
                              f"no published model has the id {identifier!r}; try search_models")
        if model.get("status") in HIDDEN_STATUSES:
            raise CorpusError("not_published",
                              f"{model.get('id')} is planned but has no specification yet")
        return model

    def resolve(self, identifier: str, include_spec: bool = False) -> dict[str, Any]:
        model = self.find(identifier)
        out = {
            "id": model.get("id"), "model_id": model.get("modelId"), "name": model.get("name"),
            "version": model.get("version"), "status": model.get("status"),
            "installable": bool(model.get("installable")), "purpose": model.get("purpose"),
            "family": model.get("family"), "category": model.get("category"),
            "domain": model.get("domain", []), "industry": model.get("industry", []),
            "requires": model.get("requires", []), "relations": model.get("relations", []),
            "research_assurance": model.get("researchAssurance"),
            "spec_url": model.get("specUrl"), "agents_url": model.get("agentsUrl"),
            "page_url": model.get("pageUrl"), "digest": model.get("digest"),
        }
        if include_spec:
            out.update(self.spec(model))
        out["citation"] = self.citation(model)
        return out

    def spec(self, model: dict[str, Any]) -> dict[str, Any]:
        url = model.get("specUrl")
        if not url:
            raise CorpusError("no_specification", f"{model.get('id')} has no specification URL")
        raw = self.fetch(url)
        if len(raw) > MAX_SPEC_BYTES:
            raise CorpusError("spec_too_large", f"{url} is larger than {MAX_SPEC_BYTES} bytes")
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        expected = model.get("digest")
        return {
            "spec": raw.decode("utf-8", errors="replace"),
            "spec_digest": digest,
            "digest_verified": expected == digest if expected else None,
        }

    def cite(self, identifier: str) -> dict[str, Any]:
        return self.citation(self.find(identifier))

    @staticmethod
    def citation(model: dict[str, Any]) -> dict[str, Any]:
        name, version = model.get("name"), model.get("version")
        text = f"{name} ({model.get('id')}, version {version}). Vercy. {model.get('pageUrl')}"
        return {"text": text, "url": model.get("pageUrl"), "spec_url": model.get("specUrl"),
                "version": version, "digest": model.get("digest")}
