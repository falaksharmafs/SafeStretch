"""Small helpers to clean messy OSM tag values (no heavy imports so they are easy to test)."""
import re


def first(v):
    if isinstance(v, (list, tuple)):
        return v[0] if v else None
    return v


def to_int(v):
    v = first(v)
    if v is None or v != v:
        return None
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


def to_bool(v):
    v = first(v)
    if v is None or v != v:
        return False
    return str(v).lower() in ("true", "yes", "1", "-1")


def to_text(v, default=None):
    v = first(v)
    if v is None or v != v or v == "":
        return default
    return str(v)
