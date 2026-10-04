"""Reading a .celeste save file (XML)."""
import xml.etree.ElementTree as ET

VANILLA_CHAPTERS = 11  # Prologue, chapters 1-7, Epilogue, Core, Farewell


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

def parse_area(area_el):
    """Return a dict for one AreaStats element, merged over its modes (A/B/C)."""
    ident = text(area_el, "SID") or text(area_el, "ID_Safe") or text(area_el, "ID")
    info = {"id": ident, "completed": False, "touched": False, "deaths": 0,
            "ticks": 0, "berries": 0, "heart": False, "modes": [], "checkpoints": {}}
    modes = child(area_el, "Modes")
    mode_els = [m for m in modes if local(m.tag) == "AreaModeStats"] if modes is not None else []
    for i, m in enumerate(mode_els):
        ticks = as_int(text(m, "TimePlayed"))
        deaths = as_int(text(m, "Deaths"))
        done = as_bool(text(m, "Completed"))
        berries = as_int(text(m, "TotalStrawberries"))
        heart = as_bool(text(m, "HeartGem"))
        side = "ABC"[i] if i < 3 else str(i)
        cps_el = child(m, "Checkpoints")
        cps = [(c.text or "").strip() for c in cps_el if local(c.tag) == "string"] if cps_el is not None else []
        if cps:
            info["checkpoints"][side] = cps
        if done or ticks > 0 or deaths > 0 or cps:
            info["touched"] = True
            info["modes"].append(side)
        info["completed"] = info["completed"] or done
        info["deaths"] += deaths
        info["ticks"] += ticks
        info["berries"] += berries
        info["heart"] = info["heart"] or heart
    return info


def parse_save(path):
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
                if not info["id"]:
                    info["id"] = f"{fallback_prefix} #{i}"
                areas.append(info)
        return areas

    sets = []
    # Vanilla chapters live in the top-level <Areas> block.
    vanilla = read_areas(child(root, "Areas"), "chapter")
    if vanilla:
        sets.append({"name": "Celeste (vanilla)", "not_loaded": False, "areas": vanilla,
                     "total": VANILLA_CHAPTERS})
    # Mod level sets. Sets Everest did not load at the last save sit in the recycle bin.
    for block, not_loaded in (("LevelSets", False), ("LevelSetRecycleBin", True)):
        block_el = child(root, block)
        if block_el is None:
            continue
        for ls in (x for x in block_el if local(x.tag) == "LevelSetStats"):
            sets.append({"name": text(ls, "Name") or "(unnamed)", "not_loaded": not_loaded,
                         "areas": read_areas(child(ls, "Areas"), "map")})
    return sets, last_area, read_session(root, sets)


SIDES = {"Normal": "A", "BSide": "B", "CSide": "C"}


def read_session(root, sets):
    """The saved mid-map session (Save & Quit), or None. One per slot, for the last-played map."""
    cs = next(iter_local(root, "CurrentSession_Safe"), None)
    if cs is None:
        cs = next(iter_local(root, "CurrentSession"), None)
    area = child(cs, "Area") if cs is not None else None
    if cs is None or area is None or not cs.get("Level"):
        return None
    sid = text(area, "SID")
    side = SIDES.get(area.get("Mode", "Normal"), "A")
    cps = []
    for st in sets:
        for a in st["areas"]:
            if a["id"] == sid:
                cps = a["checkpoints"].get(side, [])
    return {"sid": sid, "side": side, "room": cs.get("Level"),
            "start_checkpoint": cs.get("StartCheckpoint") or "",
            "deaths": as_int(cs.get("Deaths")), "checkpoints": cps}


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
