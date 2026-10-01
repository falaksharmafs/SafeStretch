from src.etl.osm_utils import to_bool, to_int, to_text
from src.suggestions import suggest


def test_to_int_handles_lists_units_and_missing():
    assert to_int("50 mph") == 50
    assert to_int(["2", "3"]) == 2
    assert to_int(None) is None
    assert to_int(float("nan")) is None


def test_to_bool_and_text():
    assert to_bool("yes") and to_bool(True) and not to_bool(None)
    assert to_text(["primary", "secondary"]) == "primary"
    assert to_text(None, "unknown") == "unknown"


def test_suggest_rules():
    tips = suggest({"junctions_nearby": 4, "alcohol_nearby": 1, "curvature": 1.3})
    assert len(tips) == 3
    assert "site audit" in suggest({})[0]
