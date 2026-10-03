"""Turn raw counts into green/amber/red checks with a plain-English reason. Thresholds mirror src/validation.py."""
from collections import namedtuple

Check = namedtuple("Check", "name status value why")   # status: ok | warn | error


def _share(n, total):
    return n / total if total else 0.0


def build_checks(f):
    """f: dict of facts from queries.health_facts()."""
    out = []
    total = f["accidents"]
    if total == 0:
        return [Check("Accident records", "error", "0", "No accidents loaded - the model has nothing to learn from.")]
    snap = _share(f["snapped"], total)
    out.append(Check("Accidents matched to a road", "ok" if snap >= 0.9 else "error", f"{snap:.1%}",
                     "At least 90% must snap to a road within the snap distance." if snap < 0.9 else "Meets the 90% minimum."))
    dup = _share(f["duplicates"], total)
    out.append(Check("Duplicate accident records", "ok" if dup <= 0.02 else "warn", f"{dup:.2%}",
                     "More than 2% share the same time and location." if dup > 0.02 else "Within the 2% tolerance."))
    out.append(Check("Accidents outside study area", "ok" if f["out_of_area"] == 0 else "warn", f"{f['out_of_area']:,}",
                     "Points fall outside the study-area polygon." if f["out_of_area"] else "All inside the study area."))
    out.append(Check("Invalid geometries", "ok" if f["invalid_geom"] == 0 else "error", f"{f['invalid_geom']:,}",
                     "Invalid geometries break spatial joins." if f["invalid_geom"] else "All geometries valid."))
    out.append(Check("Future-dated accidents", "ok" if f["future"] == 0 else "error", f"{f['future']:,}",
                     "Timestamps after now - likely a parsing or timezone error." if f["future"] else "None."))
    out.append(Check("Severity outside 1-3", "ok" if f["bad_severity"] == 0 else "error", f"{f['bad_severity']:,}",
                     "Severity must be 1 fatal, 2 serious, 3 minor." if f["bad_severity"] else "All valid."))
    roads = f["roads"]
    for col, label in (("null_speed", "speed limit"), ("null_lanes", "lane count")):
        s = _share(f[col], roads)
        out.append(Check(f"Roads missing {label}", "ok" if s <= 0.5 else "warn", f"{s:.0%}",
                         "OpenStreetMap often lacks this tag; the model treats it as missing." if s > 0.5
                         else "Acceptable coverage."))
    poi = f["poi_counts"]
    for cat in ("junction", "school", "hospital", "crossing", "bus_stop", "alcohol_outlet"):
        if poi.get(cat, 0) == 0:
            out.append(Check(f"POI category '{cat}'", "warn", "0",
                             f"No '{cat}' points loaded, so this feature is always zero for the model."))
    if f["weather"] == 0:
        out.append(Check("Weather records", "warn", "0", "Rain features and multipliers need weather history."))
    return out


def overall(checks):
    s = {c.status for c in checks}
    return "error" if "error" in s else "warn" if "warn" in s else "ok"
