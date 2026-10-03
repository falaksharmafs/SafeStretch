"""Needs a migrated PostGIS+pgRouting DB (CI provides one). Skipped automatically otherwise.
Builds a tiny diamond graph: A->B->D is short but 'risky', A->C->D is longer but 'safe'."""
import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")


@pytest.fixture()
def con():
    from src.db import get_engine
    try:
        c = get_engine().connect()
        c.exec_driver_sql("SELECT 1 FROM segment_risk LIMIT 1")
    except Exception:
        pytest.skip("database with migrations not available")
    tx = c.begin()
    yield c
    tx.rollback()
    c.close()


def _seg(con, sid, u, v, length, pct, coords):
    con.exec_driver_sql(
        "INSERT INTO road_segments (segment_id, osm_u, osm_v, road_type, length_m, geom) "
        f"VALUES ({sid}, {u}, {v}, 'primary', {length}, ST_GeomFromText('LINESTRING({coords})', 4326))")
    con.exec_driver_sql(f"INSERT INTO segment_risk (segment_id, risk_pct) VALUES ({sid}, {pct})")


def test_safest_route_avoids_risky_segments(con):
    _seg(con, 9000001, 9001, 9002, 100, 1.0, "0 0, 0.001 0.001")
    _seg(con, 9000002, 9002, 9004, 100, 1.0, "0.001 0.001, 0.002 0")
    _seg(con, 9000003, 9001, 9003, 130, 0.0, "0 0, 0.001 -0.001")
    _seg(con, 9000004, 9003, 9004, 130, 0.0, "0.001 -0.001, 0.002 0")

    fast = [r[0] for r in con.exec_driver_sql("SELECT segment_id FROM route_between(9001, 9004, 0)")]
    safe = [r[0] for r in con.exec_driver_sql("SELECT segment_id FROM route_between(9001, 9004, 3)")]
    assert fast == [9000001, 9000002]
    assert safe == [9000003, 9000004]
