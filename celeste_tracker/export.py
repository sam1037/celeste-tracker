"""The model as JSON, for the UI and other tools (PRD #10, doc/DESIGN.md "JSON export")."""
import json
from dataclasses import asdict
from datetime import datetime, timezone

SCHEMA = 2  # bump on breaking changes, so readers can tell what they got. 2: one catalog tree, progress per slot


def to_dict(lib, mods=None):
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mods_folder": str(mods.source) if mods and mods.source else None,
        **asdict(lib),
    }


def to_json(lib, mods=None):
    return json.dumps(to_dict(lib, mods), indent=2, ensure_ascii=False, default=str)
