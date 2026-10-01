CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS study_area (
    name TEXT,
    geom GEOMETRY(Geometry, 4326)
);

CREATE TABLE IF NOT EXISTS road_segments (
    segment_id   BIGSERIAL PRIMARY KEY,
    osm_u        BIGINT,
    osm_v        BIGINT,
    name         TEXT,
    road_type    TEXT,
    speed_limit  INT,
    lanes        INT,
    oneway       BOOLEAN,
    length_m     DOUBLE PRECISION,
    geom         GEOMETRY(LineString, 4326)
);

CREATE TABLE IF NOT EXISTS accidents (
    accident_id  BIGSERIAL PRIMARY KEY,
    occurred_at  TIMESTAMPTZ,
    severity     SMALLINT,          -- 1 fatal, 2 serious, 3 minor
    vehicles     INT,
    casualties   INT,
    source       TEXT,              -- file/preset name; 'synthetic' is flagged in the dashboard
    segment_id   BIGINT REFERENCES road_segments(segment_id) ON DELETE SET NULL,
    snap_dist_m  DOUBLE PRECISION,
    geom         GEOMETRY(Point, 4326)
);

CREATE TABLE IF NOT EXISTS poi (
    poi_id    BIGSERIAL PRIMARY KEY,
    category  TEXT,                 -- alcohol_outlet, school, hospital, bus_stop, crossing, junction
    geom      GEOMETRY(Point, 4326)
);

CREATE TABLE IF NOT EXISTS weather_hourly (
    hour_ts  TIMESTAMPTZ PRIMARY KEY,
    rain_mm  REAL,
    temp_c   REAL
);

-- Spatial indexes (GiST). The ::geography expression indexes serve metre-based ST_DWithin queries.
CREATE INDEX IF NOT EXISTS idx_road_segments_geom  ON road_segments USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_road_segments_geog  ON road_segments USING GIST ((geom::geography));
CREATE INDEX IF NOT EXISTS idx_accidents_geom      ON accidents     USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_accidents_segment   ON accidents (segment_id);
CREATE INDEX IF NOT EXISTS idx_accidents_time      ON accidents (occurred_at);
CREATE INDEX IF NOT EXISTS idx_poi_geom            ON poi USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_poi_geog            ON poi USING GIST ((geom::geography));
CREATE INDEX IF NOT EXISTS idx_poi_category        ON poi (category);
