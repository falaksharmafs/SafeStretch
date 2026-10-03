CREATE EXTENSION IF NOT EXISTS pgrouting;

-- Live relative risk = calibrated base probability x hour-of-day multiplier x rain multiplier.
-- It is a RELATIVE INDEX (not a probability). Traffic is surfaced as context, not in the score,
-- until you have enough history to learn its effect.
CREATE MATERIALIZED VIEW IF NOT EXISTS live_risk AS
WITH cur AS (
    SELECT EXTRACT(hour FROM now() AT TIME ZONE '{{TIMEZONE}}')::int AS hr,
           COALESCE((SELECT CASE WHEN rain_mm >= 2.5 THEN 'heavy' WHEN rain_mm >= 0.1 THEN 'light' ELSE 'dry' END
                     FROM live_conditions WHERE ts > now() - interval '3 hours'
                     ORDER BY ts DESC LIMIT 1), 'dry') AS rain_key
)
SELECT r.segment_id,
       r.risk_prob                                         AS base_prob,
       COALESCE(h.value, 1.0)                              AS time_mult,
       COALESCE(w.value, 1.0)                              AS rain_mult,
       r.risk_prob * COALESCE(h.value, 1.0) * COALESCE(w.value, 1.0) AS live_index,
       now()                                               AS computed_at
FROM segment_risk r
CROSS JOIN cur
LEFT JOIN risk_multipliers h ON h.kind = 'hour' AND h.key = cur.hr::text
LEFT JOIN risk_multipliers w ON w.kind = 'rain' AND w.key = cur.rain_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_live_risk_seg ON live_risk (segment_id);

-- Served as vector tiles by pg_tileserv (top half of segments only, keeps tiles small)
CREATE OR REPLACE VIEW risk_tiles AS
SELECT s.segment_id, COALESCE(s.name, '') AS name, s.road_type,
       r.risk_rank, r.risk_pct, r.risk_prob,
       COALESCE(l.live_index, r.risk_prob) AS live_index,
       s.geom
FROM road_segments s
JOIN segment_risk r ON r.segment_id = s.segment_id
LEFT JOIN live_risk l ON l.segment_id = s.segment_id
WHERE r.risk_pct >= 0.5;

-- Routing graph. osmnx edges are already directed (two-way streets appear twice).
CREATE OR REPLACE VIEW routing_edges AS
SELECT s.segment_id AS id, s.osm_u AS source, s.osm_v AS target, s.length_m,
       COALESCE(r.risk_pct, 0) AS risk_pct, s.geom
FROM road_segments s
LEFT JOIN segment_risk r ON r.segment_id = s.segment_id;

-- Cost = length * (1 + lam * risk_pct). lam = 0 gives the fastest (shortest) route.
CREATE OR REPLACE FUNCTION route_between(src BIGINT, dst BIGINT, lam DOUBLE PRECISION)
RETURNS TABLE (seq BIGINT, segment_id BIGINT, length_m DOUBLE PRECISION, risk_pct DOUBLE PRECISION, geom_json TEXT)
AS $$
    SELECT d.seq, e.id, e.length_m, e.risk_pct, ST_AsGeoJSON(e.geom)
    FROM pgr_dijkstra(
        format('SELECT id, source, target, length_m * (1 + %s * risk_pct) AS cost FROM routing_edges', lam),
        src, dst, true) d
    JOIN routing_edges e ON e.id = d.edge
    ORDER BY d.seq;
$$ LANGUAGE sql STABLE;
