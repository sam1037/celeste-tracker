"""The model as JSON, for the UI and other tools (PRD #10)."""
import json
from dataclasses import asdict
from datetime import datetime, timezone

SCHEMA = 1  # bump on breaking changes, so readers can tell what they got


def to_dict(slots, mods=None):
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mods_folder": str(mods.source) if mods and mods.source else None,
        "slots": [asdict(s) for s in slots],
    }


def to_json(slots, mods=None):
    return json.dumps(to_dict(slots, mods), indent=2, ensure_ascii=False, default=str)
