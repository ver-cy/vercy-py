"""Regenerate src/vercy/data/profile.json from src/vercy/data/profile.yaml.

Development only (needs PyYAML). Run after copying a new profile.yaml from
https://ver.cy/overlay/profile.yaml:

    python tools/sync_profile.py
"""
import json
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parents[1] / "src" / "vercy" / "data"
profile = yaml.safe_load((DATA / "profile.yaml").read_text(encoding="utf-8"))
(DATA / "profile.json").write_text(
    json.dumps(profile, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")
print(f"profile.json: {profile['overlay']} {profile['version']}, {len(profile['fields'])} fields")
