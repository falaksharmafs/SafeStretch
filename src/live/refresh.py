"""Recompute the live_risk materialized view (hour-of-day + current rain multipliers)."""
from ..db import get_engine


def main():
    raw = get_engine().raw_connection()
    try:
        raw.autocommit = True            # REFRESH ... CONCURRENTLY cannot run inside a transaction block
        with raw.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY live_risk")
    finally:
        raw.close()
    print("live_risk refreshed")


if __name__ == "__main__":
    main()
