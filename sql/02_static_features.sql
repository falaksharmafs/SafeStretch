-- Per-segment features that do NOT depend on accidents.
DROP TABLE IF EXISTS segment_static_features;
CREATE TABLE segment_static_features AS
SELECT
    s.segment_id,
    s.road_type,
    s.speed_limit,
    s.lanes,
    s.oneway,
    s.length_m,
    -- curvature: path length / straight-line distance (1.0 = straight)
    COALESCE(
        ST_Length(s.geom::geography) /
        NULLIF(ST_Distance(ST_StartPoint(s.geom)::geography, ST_EndPoint(s.geom)::geography), 0),
        1.0) AS curvature,
    ST_Y(ST_Centroid(s.geom)) AS lat,
    ST_X(ST_Centroid(s.geom)) AS lon,
    c.alcohol_nearby, c.junctions_nearby, c.schools_nearby,
    c.hospitals_nearby, c.bus_stops_nearby, c.crossings_nearby
FROM road_segments s
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE p.category = 'alcohol_outlet') AS alcohol_nearby,
        COUNT(*) FILTER (WHERE p.category = 'junction')       AS junctions_nearby,
        COUNT(*) FILTER (WHERE p.category = 'school')         AS schools_nearby,
        COUNT(*) FILTER (WHERE p.category = 'hospital')       AS hospitals_nearby,
        COUNT(*) FILTER (WHERE p.category = 'bus_stop')       AS bus_stops_nearby,
        COUNT(*) FILTER (WHERE p.category = 'crossing')       AS crossings_nearby
    FROM poi p
    WHERE ST_DWithin(s.geom::geography, p.geom::geography, {{POI_RADIUS_M}})
) c ON TRUE;

ALTER TABLE segment_static_features ADD PRIMARY KEY (segment_id);
ANALYZE segment_static_features;
