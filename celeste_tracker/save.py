"""Reading a .celeste save file (XML)."""
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------- XML helpers

def local(tag):
    return tag.split("}", 1)[-1]


def child(el, name):
    for c in el:
        if local(c.tag) == name:
            return c
    return None


def text(el, name, default=""):
    """Value of `name` on `el`, as an XML attribute first, else as a child element's text."""
    attr = el.get(name)
    if attr is not None:
        return attr.strip()
    c = child(el, name)
    return (c.text or default).strip() if c is not None and c.text else default


def as_int(s, default=0):
    try:
        return int(s)
    except (TypeError, ValueError):
        return default


def as_bool(s):
    return str(s).strip().lower() == "true"


def iter_local(root, name):
    return (e for e in root.iter() if local(e.tag) == name)


# ---------------------------------------------------------------- parsing
#
# The parser returns plain dicts that mirror the save, one entry per side. It doesn't decide
# which sides exist or what is "completed": that is model.py and rules.py.

VANILLA_SET = "Celeste (vanilla)"
SIDES = {"Normal": "A", "BSide": "B", "CSide": "C"}


def parse_side(m, side):
    """One AreaModeStats element."""
    cps_el = child(m, "Checkpoints")
    cps = [(c.text or "").strip() for c in cps_el if local(c.tag) == "string"] if cps_el is not None else []
    s = {"side": side,
         "cleared": as_bool(text(m, "Completed")),
         "heart": as_bool(text(m, "HeartGem")),
         "deaths": as_int(text(m, "Deaths")),
         "ticks": as_int(text(m, "TimePlayed")),
         "best_ticks": as_int(text(m, "BestTime")),
         "best_deaths": as_int(text(m, "BestDeaths")),
         "berries": as_int(text(m, "TotalStrawberries")),
         "checkpoints": cps}
    s["opened"] = bool(s["cleared"] or s["heart"] or s["ticks"] or s["deaths"] or cps)
    return s


def parse_area(area_el):
    """One AreaStats element: the map's SID and its sides. The save always lists A, B and C."""
    sid = text(area_el, "SID") or text(area_el, "ID_Safe") or text(area_el, "ID")
    modes = child(area_el, "Modes")
    mode_els = [m for m in modes if local(m.tag) == "AreaModeStats"] if modes is not None else []
    return {"sid": sid, "sides": [parse_side(m, "ABC"[i]) for i, m in enumerate(mode_els[:3])]}


def parse_save(path):
    """The whole slot: {'name', 'last_area', 'session', 'sets': [{'name', 'loaded', 'vanilla', 'areas'}]}."""
    root = ET.parse(path).getroot()
    last_area = ""
    la = next(iter_local(root, "LastArea_Safe"), None)
    if la is None:
        la = next(iter_local(root, "LastArea"), None)
    if la is not None:
        last_area = text(la, "SID") or (la.text or "").strip()

    def read_areas(areas_el, fallback_prefix):
        areas = []
        if areas_el is not None:
            for i, a in enumerate(x for x in areas_el if local(x.tag) == "AreaStats"):
                info = parse_area(a)
                if not info["sid"]:
                    info["sid"] = f"{fallback_prefix} #{i}"
                areas.append(info)
        return areas

    sets = []
    # Vanilla chapters live in the top-level <Areas> block.
    vanilla = read_areas(child(root, "Areas"), "chapter")
    if vanilla:
        sets.append({"name": VANILLA_SET, "loaded": True, "vanilla": True, "areas": vanilla})
    # Mod level sets. Sets Everest did not load at the last save sit in the recycle bin.
    for block, loaded in (("LevelSets", True), ("LevelSetRecycleBin", False)):
        block_el = child(root, block)
        if block_el is None:
            continue
        for ls in (x for x in block_el if local(x.tag) == "LevelSetStats"):
            name = text(ls, "Name") or "(unnamed)"
            if name == "Celeste":  # vanilla's own entry here is empty; its chapters were read above
                continue
            sets.append({"name": name, "loaded": loaded, "vanilla": False,
                         "areas": read_areas(child(ls, "Areas"), "map")})
    return {"name": text(root, "Name"), "last_area": last_area, "session": read_session(root), "sets": sets}


def read_session(root):
    """The saved mid-map session (Save & Quit), or None. One per slot, for the last-played map."""
    cs = next(iter_local(root, "CurrentSession_Safe"), None)
    if cs is None:
        cs = next(iter_local(root, "CurrentSession"), None)
    area = child(cs, "Area") if cs is not None else None
    if cs is None or area is None or not cs.get("Level"):
        return None
    return {"sid": text(area, "SID"), "side": SIDES.get(area.get("Mode", "Normal"), "A"),
            "room": cs.get("Level"), "start_checkpoint": cs.get("StartCheckpoint") or "",
            "deaths": as_int(cs.get("Deaths"))}


def dump(path, depth=7, per_tag=2):
    """Print the XML structure with attributes, showing at most `per_tag` siblings of each tag."""
    root = ET.parse(path).getroot()

    def walk(el, d):
        if d > depth:
            return
        t = (el.text or "").strip()
        attrs = "".join(f" [{k}={v[:40]}]" for k, v in el.attrib.items())
        print("  " * d + local(el.tag) + attrs + (f" = {t[:40]}" if t else ""))
        counts = {}
        for c in el:
            tag = local(c.tag)
            counts[tag] = counts.get(tag, 0) + 1
            if counts[tag] <= per_tag:
                walk(c, d + 1)
        for tag, n in counts.items():
            if n > per_tag:
                print("  " * (d + 1) + f"... (+{n - per_tag} more <{tag}>)")

    walk(root, 0)
