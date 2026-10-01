-- Resume evidence: run this file in psql and paste the timings into your README.
-- KNN snap of 500 accidents, with and without the GiST index.

EXPLAIN (ANALYZE, BUFFERS)
SELECT a.accident_id,
       (SELECT s.segment_id FROM road_segments s ORDER BY s.geom <-> a.geom LIMIT 1)
FROM (SELECT * FROM accidents LIMIT 500) a;

DROP INDEX IF EXISTS idx_road_segments_geom;

EXPLAIN (ANALYZE, BUFFERS)
SELECT a.accident_id,
       (SELECT s.segment_id FROM road_segments s ORDER BY s.geom <-> a.geom LIMIT 1)
FROM (SELECT * FROM accidents LIMIT 500) a;

CREATE INDEX idx_road_segments_geom ON road_segments USING GIST (geom);
ANALYZE road_segments;
