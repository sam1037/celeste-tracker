"""The user's own data. For now: notes in a JSON file."""
import json
import sys
from pathlib import Path

DEFAULT_NOTES = Path(__file__).resolve().parent.parent / "celeste_notes.json"


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        sys.exit(f"{path} is not valid JSON ({e}). Fix or delete it and run again.")


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
