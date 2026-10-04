"""The data model: Slot > LevelSet > Map > Side. The side is the unit of progress (doc/PRD.md).

build_slot() combines the parsed save with what the Mods folder knows: which maps a set has and which
sides each map has. Statuses and totals are filled in by rules.apply().
"""
from dataclasses import dataclass, field
from pathlib import Path


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
class Side:
    side: str                    # 'A', 'B' or 'C'
    exists: bool | None          # from the mod's .bin files or the vanilla list; None = unknown
    has_heart: bool | None       # None = unknown (mods, until map .bin parsing)
    opened: bool = False
    cleared: bool = False
    heart: bool = False
    deaths: int = 0
    ticks: int = 0
    best_ticks: int = 0
    best_deaths: int = 0
    berries: int = 0
    checkpoints: list[Checkpoint] = field(default_factory=list)
    status: str = ""             # rules.SIDE_STATUSES


@dataclass
class Map:
    sid: str
    title: str
    sides: dict[str, Side]       # only sides that exist or were opened
    status: str = ""             # rules.MAP_STATUSES


@dataclass
class LevelSet:
    name: str
    title: str
    mod_name: str
    loaded: bool                 # False: Everest didn't load the mod at the last save (recycle bin)
    vanilla: bool
    sides_known: bool            # the set's maps and sides come from mod files (or the vanilla list)
    maps: list[Map]
    last_played: bool = False
    # Filled in by rules.apply():
    status: str = ""
    sides_done: int = 0
    sides_no_heart: int = 0
    sides_total: int = 0
    maps_done: int = 0
    maps_total: int = 0
    deaths: int = 0
    ticks: int = 0
    berries: int = 0
    open_checkpoints: int = 0    # checkpoints reached in sides not yet completed
    latest_checkpoint: dict | None = None  # {'sid', 'side', 'room', 'title'}

    def find_map(self, sid):
        return next((m for m in self.maps if m.sid == sid), None)


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
    number: int | None
    path: Path
    name: str
    last_played_sid: str
    session: Session | None
    sets: list[LevelSet]


def build_slot(raw, mods, number=None, path=None):
    sets = [build_set(rs, mods) for rs in raw["sets"]]
    last = raw["last_area"]
    for s in sets:
        s.last_played = bool(last) and s.find_map(last) is not None
    session = None
    if raw["session"]:
        rs = raw["session"]
        side = next((m.sides.get(rs["side"]) for s in sets for m in s.maps if m.sid == rs["sid"]), None)
        session = Session(rs["sid"], rs["side"], rs["room"], rs["start_checkpoint"], rs["deaths"],
                          title=map_title(rs["sid"], mods), checkpoints=side.checkpoints if side else [])
    return Slot(number, Path(path) if path else None, raw["name"], last, session, sets)


def map_title(sid, mods):
    return VANILLA[sid][0] if sid in VANILLA else mods.title(sid)


def build_set(rs, mods):
    if rs["vanilla"]:
        known = {sid: (set(sides), heart) for sid, (_, sides, heart) in VANILLA.items()}
    else:
        known = {sid: (sides, None) for sid, sides in mods.maps.get(rs["name"], {}).items()}
    by_sid = {a["sid"]: a for a in rs["areas"]}
    order = list(by_sid) + sorted(known.keys() - by_sid.keys())
    maps = []
    for sid in order:
        exists_in, has_heart = known.get(sid, (None, None))
        saved = {s["side"]: s for s in by_sid[sid]["sides"]} if sid in by_sid else {}
        sides = {}
        for letter in "ABC":
            raw_side = saved.get(letter)
            opened = bool(raw_side and raw_side["opened"])
            exists = (letter in exists_in) if exists_in is not None else None
            if not (exists or opened):  # the save's placeholder records for sides a map doesn't have
                continue
            side = Side(letter, exists, has_heart)
            if raw_side:
                for k in ("opened", "cleared", "heart", "deaths", "ticks", "best_ticks", "best_deaths", "berries"):
                    setattr(side, k, raw_side[k])
                side.checkpoints = [Checkpoint(r, mods.checkpoint(sid, r)) for r in raw_side["checkpoints"]]
            sides[letter] = side
        maps.append(Map(sid, map_title(sid, mods), sides))
    return LevelSet(name=rs["name"], title="" if rs["vanilla"] else mods.title(rs["name"]),
                    mod_name="" if rs["vanilla"] else mods.mod_of.get(rs["name"], ""),
                    loaded=rs["loaded"], vanilla=rs["vanilla"], sides_known=bool(known), maps=maps)
