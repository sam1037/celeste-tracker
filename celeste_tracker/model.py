"""The data model (doc/DESIGN.md, "Data model"): one catalog of what exists, with each slot's progress on it.

Catalog: Mod > LevelSet > Chapter > Side, built once from the Mods folder, the vanilla list and the chapters
the slots mention, leaving out collab gyms (is_gym). Progress: each Side has one View per slot that has a
record of it (keyed by slot key). rules.apply() then fills in statuses and totals, and the "all" (all slots
combined) views.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

VANILLA_MOD = "Celeste"
VANILLA_SET = "Celeste (vanilla)"

# Collab gyms: tutorial level sets that can't be completed, so they're left out of the catalog (not shown, not
# counted). A level set is a gym when the last part of its name is "Gyms", after an optional number prefix.
# In my Mods folder and saves (2026-10-05) that is exactly SpringCollab2020/0-Gyms, StrawberryJam2021/0-Gyms,
# CatCollab/0-Gyms and SecretSanta2024/3-Hard/WatchtowerContest/0-Gyms.
GYM_SET = re.compile(r"(\d+-)?gyms", re.I)


def is_gym(set_name):
    return bool(GYM_SET.fullmatch(set_name.rpartition("/")[2]))

# Collab lobbies (CollabUtils2): the hub maps that lead to a collab's chapters. Real maps with their own deaths,
# time and clears, so they stay and count, but their level set's title gets " (lobby)": the mods title it after
# the collab itself, so it read like a copy of the mod. In my Mods folder and saves (2026-10-07) every lobby level
# set is named exactly <collab>/0-Lobbies (25 mods, e.g. SpringCollab2020, StrawberryJam2021, ABuffZucchiniCollab).
LOBBY_SET = re.compile(r"(\d+-)?lobbies", re.I)


def is_lobby(set_name):
    return bool(LOBBY_SET.fullmatch(set_name.rpartition("/")[2]))


def set_title(set_name, title):
    """The level set's title as shown: its in-game title, marked when it's a collab lobby."""
    return f"{title} (lobby)" if title and is_lobby(set_name) else title

# Vanilla chapters: SID -> (title, sides, has a heart). Verified on 32 real save slots: these three
# chapters are stored with HeartGem=false even when cleared, and only chapters 1-7 and Core have B/C sides.
VANILLA = {
    "Celeste/0-Intro": ("Prologue", "A", False),
    "Celeste/1-ForsakenCity": ("Forsaken City", "ABC", True),
    "Celeste/2-OldSite": ("Old Site", "ABC", True),
    "Celeste/3-CelestialResort": ("Celestial Resort", "ABC", True),
    "Celeste/4-GoldenRidge": ("Golden Ridge", "ABC", True),
    "Celeste/5-MirrorTemple": ("Mirror Temple", "ABC", True),
    "Celeste/6-Reflection": ("Reflection", "ABC", True),
    "Celeste/7-Summit": ("The Summit", "ABC", True),
    "Celeste/8-Epilogue": ("Epilogue", "A", False),
    "Celeste/9-Core": ("Core", "ABC", True),
    "Celeste/LostLevels": ("Farewell", "A", False),
}


@dataclass
class Checkpoint:
    room: str
    title: str = ""


@dataclass
class View:
    """Status and totals of one node (mod, level set, chapter or side) for one slot, or for all slots ("all": the mod's furthest slot).
    A side's view counts the side itself (sides_total 1), so every node's totals are sums over its sides."""
    status: str = ""
    sides_done: int = 0
    hearts: int = 0                     # sides whose crystal heart was collected (not part of "completed")
    sides_total: int = 0
    by_side: dict[str, list[int]] = field(default_factory=dict)  # 'A'/'B'/'C' -> [done, total] (not on sides)
    maps_done: int = 0
    maps_total: int = 0
    deaths: int = 0
    ticks: int = 0
    berries: int = 0
    open_checkpoints: int = 0           # checkpoints reached in sides not yet completed
    latest_checkpoint: dict | None = None  # {'sid', 'side', 'room', 'title'}
    loaded: bool = True                 # False: Everest didn't load the mod at the last save (recycle bin)
    slots: list[str] = field(default_factory=list)  # slots with progress here
    slot: str | None = None             # "all" views only: the slot shown, the mod's furthest (rules.furthest_slot)
    # Sides only:
    cleared: bool = False
    heart: bool = False
    best_ticks: int = 0
    best_deaths: int = 0
    checkpoints: list[Checkpoint] = field(default_factory=list)


@dataclass
class Side:
    side: str                    # 'A', 'B' or 'C'
    exists: bool | None          # from the mod's .bin files or the vanilla list; None = unknown
    has_heart: bool | None       # None = unknown (mods). Information only: completion doesn't depend on hearts
    progress: dict[str, View] = field(default_factory=dict)  # slot key or "all" -> view


@dataclass
class Chapter:                   # what modders call a map; keyed by its SID
    sid: str
    title: str
    sides: dict[str, Side]
    progress: dict[str, View] = field(default_factory=dict)
    user: dict = field(default_factory=dict)  # the player's own fields (store.FIELDS), keyed by SID


@dataclass
class LevelSet:
    name: str
    title: str
    chapters: list[Chapter]      # the chapters of this level set that this mod provides
    progress: dict[str, View] = field(default_factory=dict)
    user: dict = field(default_factory=dict)  # keyed by level set name


@dataclass
class Mod:
    id: str                      # everest.yaml Name; "Celeste" for vanilla; the level set name if no mod was found
    name: str                    # what players see (doc/DESIGN.md, "Mod names")
    name_source: str             # renamed | gamebanana | map title | level set title | mod id | vanilla
    gamebanana_title: str
    found: bool                  # in the Mods folder (or vanilla): its chapters and sides are known
    vanilla: bool
    sets: list[LevelSet]
    progress: dict[str, View] = field(default_factory=dict)
    user: dict = field(default_factory=dict)  # keyed by mod ID; 'rename' wins over every other name

    def chapters(self):
        return [ch for ls in self.sets for ch in ls.chapters]

    def find_chapter(self, sid):
        return next((ch for ch in self.chapters() if ch.sid == sid), None)


@dataclass
class Session:
    sid: str
    side: str
    room: str
    start_checkpoint: str
    deaths: int
    title: str = ""
    checkpoints: list[Checkpoint] = field(default_factory=list)


@dataclass
class Slot:
    key: str                     # "1" for 1.celeste; the file name for any other file
    number: int | None
    path: Path
    name: str
    last_played_sid: str
    session: Session | None
    not_loaded: list[str]        # level sets in the recycle bin


@dataclass
class Library:
    slots: list[Slot]
    mods: list[Mod]


def slot_key(number, path):
    return str(number) if number is not None else Path(path).stem


class _Builder:
    """Collects the catalog: mods, their level sets and chapters, without duplicates."""

    def __init__(self, mods_info):
        self.info = mods_info
        self.mods = {}      # mod ID -> {'found', 'vanilla', 'sets': {set name: {sid: Chapter}}}
        self.chapters = {}  # sid -> Chapter

    def add(self, mod_id, set_name, sid, sides, has_heart, found, vanilla=False, title=None):
        mod = self.mods.setdefault(mod_id, {"found": found, "vanilla": vanilla, "sets": {}})
        exists = None if sides is None else True
        ch = Chapter(sid, self.info.title(sid) if title is None else title,
                     {s: Side(s, exists, has_heart) for s in "ABC" if sides and s in sides})
        mod["sets"].setdefault(set_name, {})[sid] = ch
        self.chapters[sid] = ch
        return ch


def build_library(loaded, mods_info, titles=None, user=None):
    """loaded: [(slot number, path, parse_save() result)]. titles: {mod ID: {'title', 'author'}} (moddb).
    user: {mod ID / level set / chapter SID: fields} (store.user_fields)."""
    titles, user = titles or {}, user or {}
    b = _Builder(mods_info)
    for sid, (title, sides, heart) in VANILLA.items():
        b.add(VANILLA_MOD, VANILLA_SET, sid, set(sides), heart, found=True, vanilla=True, title=title)
    for set_name, chapters in mods_info.maps.items():
        if is_gym(set_name):
            continue
        for sid, sides in sorted(chapters.items()):
            b.add(mods_info.owner[sid], set_name, sid, sides, None, found=True)

    slots = []
    for number, path, raw in loaded:
        key = slot_key(number, path)
        for rs in raw["sets"]:
            if is_gym(rs["name"]):
                continue
            for area in rs["areas"]:
                opened = [s for s in area["sides"] if s["opened"]]
                if not opened:
                    continue
                ch = b.chapters.get(area["sid"])
                if ch is None:  # no mod in the Mods folder has it: a mod of its own, named after its level set
                    owner = VANILLA_MOD if rs["vanilla"] else rs["name"]
                    ch = b.add(owner, rs["name"], area["sid"], None, None, found=rs["vanilla"], vanilla=rs["vanilla"])
                for s in opened:
                    side = ch.sides.get(s["side"])
                    if side is None:  # opened in the save, but the mod files don't have it (or are unknown)
                        known = next(iter(ch.sides.values())).exists if ch.sides else None
                        side = ch.sides.setdefault(s["side"], Side(s["side"], False if known else None, None))
                    side.progress[key] = View(
                        cleared=s["cleared"], heart=s["heart"], deaths=s["deaths"], ticks=s["ticks"],
                        best_ticks=s["best_ticks"], best_deaths=s["best_deaths"], berries=s["berries"],
                        checkpoints=[Checkpoint(r, mods_info.checkpoint(ch.sid, r)) for r in s["checkpoints"]],
                        slots=[key])
                ch.sides = dict(sorted(ch.sides.items()))
        session = None
        if raw["session"]:
            rs = raw["session"]
            ch = b.chapters.get(rs["sid"])
            side = ch.sides.get(rs["side"]) if ch else None
            view = side.progress.get(key) if side else None
            session = Session(rs["sid"], rs["side"], rs["room"], rs["start_checkpoint"], rs["deaths"],
                              title=ch.title if ch else "", checkpoints=view.checkpoints if view else [])
        slots.append(Slot(key, number, Path(path), raw["name"], raw["last_area"], session,
                          [rs["name"] for rs in raw["sets"] if not rs["loaded"]]))

    mods = []
    for mod_id, m in sorted(b.mods.items()):
        sets = [LevelSet(name, "" if m["vanilla"] else set_title(name, mods_info.title(name)), list(chs.values()),
                         user=user.get(name, {}))
                for name, chs in sorted(m["sets"].items())]
        if not any(ls.chapters for ls in sets):
            continue
        for ch in (ch for ls in sets for ch in ls.chapters):
            ch.user = user.get(ch.sid, {})
        gb = titles.get(mod_id, {}).get("title", "")
        mine = user.get(mod_id, {})
        name, source = (mine["rename"], "renamed") if mine.get("rename") else mod_name(mod_id, m["vanilla"], gb, sets)
        mods.append(Mod(mod_id, name, source, gb, m["found"], m["vanilla"], sets, user=mine))
    return Library(slots, mods)


def mod_name(mod_id, vanilla, gamebanana_title, sets):
    """The first available of: GameBanana title, the chapter's title (one chapter), the level set's title
    (one level set), the mod ID."""
    if vanilla:
        return VANILLA_MOD, "vanilla"
    if gamebanana_title:
        return gamebanana_title, "gamebanana"
    chapters = [ch for ls in sets for ch in ls.chapters]
    if len(chapters) == 1 and chapters[0].title:
        return chapters[0].title, "map title"
    if len(sets) == 1 and sets[0].title:
        return sets[0].title, "level set title"
    return mod_id, "mod id"
