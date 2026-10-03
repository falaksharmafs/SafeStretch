"""Optional live traffic via TomTom Flow API (free tier). Set TOMTOM_KEY. Samples the top-N riskiest segments.
Congestion is shown as CONTEXT in the API; it is not in the score until you have history to learn its effect."""
import os
import time

import requests

URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"


def parse_flow(j):
    d = j["flowSegmentData"]
    cur, free = float(d["currentSpeed"]), float(d["freeFlowSpeed"])
    return cur, free, (cur / free if free else None)


def main():
    key = os.getenv("TOMTOM_KEY")
    if not key:
        print("TOMTOM_KEY not set - skipping live traffic")
        return
    import pandas as pd
    from sqlalchemy import text

    from ..db import get_engine
    n = int(os.getenv("TRAFFIC_TOP_N", "100"))
    eng = get_engine()
    segs = pd.read_sql(text("SELECT r.segment_id, f.lat, f.lon FROM segment_risk r "
                            "JOIN segment_static_features f USING (segment_id) ORDER BY r.risk_rank LIMIT :n"),
                       eng, params={"n": n})
    rows = []
    for s in segs.itertuples():
        try:
            resp = requests.get(URL, params={"point": f"{s.lat},{s.lon}", "key": key}, timeout=15)
            resp.raise_for_status()
            cur, free, ratio = parse_flow(resp.json())
            rows.append({"segment_id": int(s.segment_id), "current_speed": cur, "free_flow_speed": free,
                         "congestion_ratio": ratio})
        except Exception as e:      # one failed point must not kill the job
            print(f"traffic skip {s.segment_id}: {e}")
        time.sleep(0.25)            # stay under the free-tier rate limit
    if rows:
        with eng.begin() as con:
            con.execute(text("INSERT INTO live_traffic (segment_id, ts, current_speed, free_flow_speed, congestion_ratio) "
                             "VALUES (:segment_id, date_trunc('minute', now()), :current_speed, :free_flow_speed, "
                             ":congestion_ratio) ON CONFLICT DO NOTHING"), rows)
            con.execute(text("DELETE FROM live_traffic WHERE ts < now() - interval '2 days'"))
    print(f"stored {len(rows)} traffic samples")


if __name__ == "__main__":
    main()
