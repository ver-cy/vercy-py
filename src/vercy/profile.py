"""The Governance Overlay profile, bundled so the checker works offline.

`data/profile.json` is generated from `data/profile.yaml` (the file published at
https://ver.cy/overlay/profile.yaml) by `tools/sync_profile.py`. The package has no
runtime dependencies, so it reads the JSON form.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

PROFILE_URL = "https://ver.cy/overlay/profile.yaml"


@lru_cache(maxsize=1)
def load_profile() -> dict[str, Any]:
    text = resources.files("vercy").joinpath("data/profile.json").read_text(encoding="utf-8")
    return json.loads(text)


def overlay_profile() -> dict[str, Any]:
    """The profile with its canonical source, as the MCP tool returns it."""
    profile = dict(load_profile())
    profile["source_url"] = PROFILE_URL
    return profile
