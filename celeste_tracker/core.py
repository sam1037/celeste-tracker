"""The entry point for front ends: files in, a finished model out. Front ends never parse files themselves."""
import sys
import xml.etree.ElementTree as ET

from . import rules
from .model import build_slot
from .save import parse_save


def load_slot(path, mods, number=None):
    return rules.apply(build_slot(parse_save(path), mods, number, path))


def load_slots(slot_paths, mods):
    """[(number, path)] -> [Slot]. A slot that can't be read (e.g. the game is writing it right now) is
    skipped with a warning when there are several; a single one stops with an error."""
    slots = []
    for n, p in slot_paths:
        try:
            slots.append(load_slot(p, mods, n))
        except (ET.ParseError, OSError) as e:
            if len(slot_paths) == 1:
                sys.exit(f"Could not read {p}: {e}")
            print(f"Warning: skipping {p}, it could not be read ({e}).", file=sys.stderr)
    return slots
