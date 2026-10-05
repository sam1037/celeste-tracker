"""The entry point for front ends: files in, a finished model out. Front ends never parse files themselves."""
import sys
import xml.etree.ElementTree as ET

from . import rules
from .model import build_library
from .save import parse_save


def read_slots(slot_paths):
    """[(number, path)] -> [(number, path, parsed save)]. A slot that can't be read (e.g. the game is writing it
    right now) is skipped with a warning when there are several; a single one stops with an error."""
    loaded = []
    for n, p in slot_paths:
        try:
            loaded.append((n, p, parse_save(p)))
        except (ET.ParseError, OSError) as e:
            if len(slot_paths) == 1:
                sys.exit(f"Could not read {p}: {e}")
            print(f"Warning: skipping {p}, it could not be read ({e}).", file=sys.stderr)
    return loaded


def build(loaded, mods, titles=None, user=None):
    """Parsed slots + mod data + the player's fields -> Library with statuses and totals for each slot and for
    all slots combined. Cheap: the UI server calls it again after every edit."""
    return rules.apply(build_library(loaded, mods, titles, user))


def load_library(slot_paths, mods, titles=None, user=None):
    return build(read_slots(slot_paths), mods, titles, user)
