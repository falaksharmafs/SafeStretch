SET TIME ZONE '{{TIMEZONE}}';

-- 1) Snap every accident to its nearest road segment (KNN via the GiST index).
--    Note: a correlated subquery is used because UPDATE ... FROM LATERAL cannot reference the target table.
UPDATE accidents a
SET segment_id = (
    SELECT s.segment_id FROM road_segments s ORDER BY s.geom <-> a.geom LIMIT 1
);

UPDATE accidents a
SET snap_dist_m = ST_Distance(a.geom::geography, s.geom::geography)
FROM road_segments s
WHERE s.segment_id = a.segment_id;

-- Drop matches that are too far from any road (bad coordinates / off-network)
UPDATE accidents SET segment_id = NULL WHERE snap_dist_m > {{SNAP_MAX_M}};

-- 2) Segment x quarter history
DROP TABLE IF EXISTS segment_period_counts;
CREATE TABLE segment_period_counts AS
SELECT
    a.segment_id,
    date_trunc('quarter', a.occurred_at)::date AS period_start,
    COUNT(*)                                        AS n_acc,
    COUNT(*) FILTER (WHERE a.severity <= 2)         AS n_serious,
    COUNT(*) FILTER (WHERE EXTRACT(hour FROM a.occurred_at) NOT BETWEEN 6 AND 19) AS n_night,
    COUNT(*) FILTER (WHERE w.rain_mm > 0.1)         AS n_rain
FROM accidents a
LEFT JOIN weather_hourly w ON w.hour_ts = date_trunc('hour', a.occurred_at)
WHERE a.segment_id IS NOT NULL
GROUP BY 1, 2;

CREATE INDEX ON segment_period_counts (segment_id);
CREATE INDEX ON segment_period_counts (period_start);
ANALYZE accidents;
ANALYZE segment_period_counts;
