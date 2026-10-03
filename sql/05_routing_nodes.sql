-- Re-run after loading roads. Nearest-node lookup table for the routing API.
DROP TABLE IF EXISTS road_nodes;
CREATE TABLE road_nodes AS
SELECT node_id, (array_agg(geom))[1] AS geom
FROM (
    SELECT osm_u AS node_id, ST_StartPoint(geom) AS geom FROM road_segments
    UNION ALL
    SELECT osm_v AS node_id, ST_EndPoint(geom)   AS geom FROM road_segments
) t
GROUP BY node_id;
ALTER TABLE road_nodes ADD PRIMARY KEY (node_id);
CREATE INDEX idx_road_nodes_geom ON road_nodes USING GIST (geom);
ANALYZE road_nodes;
