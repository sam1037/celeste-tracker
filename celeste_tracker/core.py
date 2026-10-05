"""The entry point for front ends: files in, a finished model out. Front ends never parse files themselves."""
import sys
import xml.etree.ElementTree as ET

from . import rules
from .model import build_library
from .save import parse_save


def load_library(slot_paths, mods, titles=None):
    """[(number, path)] -> Library with statuses and totals for each slot and for all slots combined.
    A slot that can't be read (e.g. the game is writing it right now) is skipped with a warning when there
    are several; a single one stops with an error."""
    loaded = []
    for n, p in slot_paths:
        try:
            loaded.append((n, p, parse_save(p)))
        except (ET.ParseError, OSError) as e:
            if len(slot_paths) == 1:
                sys.exit(f"Could not read {p}: {e}")
            print(f"Warning: skipping {p}, it could not be read ({e}).", file=sys.stderr)
    return rules.apply(build_library(loaded, mods, titles))
