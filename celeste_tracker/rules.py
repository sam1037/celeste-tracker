"""Status of each level set, from the parsed save and mod data."""


def summarize(sets, last_area, mods):
    rows = []
    for s in sets:
        touched = [a for a in s["areas"] if a["touched"]]
        if not touched:
            continue
        done = sum(1 for a in touched if a["completed"])
        in_prog = [a for a in touched if not a["completed"]]
        total = s.get("total") or mods.total(s["name"])
        if total:
            total = max(total, len(touched))
            status = "complete" if done >= total else ("in progress" if done else "started")
        elif done and not in_prog:
            status = "all opened done"
        elif done:
            status = "in progress"
        else:
            status = "started"
        # Latest checkpoint: from the unfinished map with checkpoints you've played longest.
        cands = [a for a in in_prog if a["checkpoints"]]
        latest, latest_title = "", ""
        if cands:
            best = max(cands, key=lambda a: a["ticks"])
            latest = best["checkpoints"][list(best["checkpoints"])[-1]][-1]
            latest_title = mods.checkpoint(best["id"], latest)
        rows.append({
            "latest_ckpt": latest_title or latest,
            "name": s["name"],
            "title": mods.title(s["name"]),
            "not_loaded": s["not_loaded"],
            "total": total,
            "opened": len(touched),
            "done": done,
            "status": status,
            "deaths": sum(a["deaths"] for a in touched),
            "ticks": sum(a["ticks"] for a in touched),
            "berries": sum(a["berries"] for a in touched),
            "completed_maps": [a["id"] for a in touched if a["completed"]],
            "unfinished": [a["id"] for a in in_prog],
            "checkpoints": {a["id"]: a["checkpoints"] for a in touched if a["checkpoints"]},
            "ckpt_count": sum(len(c) for a in in_prog for c in a["checkpoints"].values()),
            "is_last": bool(last_area) and any(a["id"] == last_area for a in s["areas"]),
        })
    rows.sort(key=lambda r: (-int(r["is_last"]), -r["ticks"]))
    return rows
