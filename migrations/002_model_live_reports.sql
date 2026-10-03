-- Model outputs (written by training jobs with TRUNCATE + append, so views never break)
CREATE TABLE IF NOT EXISTS segment_risk (
    segment_id   BIGINT PRIMARY KEY REFERENCES road_segments(segment_id) ON DELETE CASCADE,
    risk_score   DOUBLE PRECISION,      -- raw model output
    risk_prob    DOUBLE PRECISION,      -- isotonic-calibrated P(serious accident next quarter)
    risk_pct     DOUBLE PRECISION,      -- 1 = riskiest segment, 0 = safest (used for routing cost)
    risk_rank    INT,
    reason_1     TEXT, reason_2 TEXT, reason_3 TEXT,
    as_of_period DATE
);
CREATE INDEX IF NOT EXISTS idx_segment_risk_rank ON segment_risk (risk_rank);

-- Empirical-Bayes black-spot ranking (exposure-adjusted)
CREATE TABLE IF NOT EXISTS segment_eb (
    segment_id    BIGINT PRIMARY KEY,
    exposure      DOUBLE PRECISION,
    observed      INT,
    expected_rate DOUBLE PRECISION,
    eb_estimate   DOUBLE PRECISION,
    eb_rank       INT
);

-- Learned relative-rate multipliers for live scoring (kind = 'hour' | 'rain')
CREATE TABLE IF NOT EXISTS risk_multipliers (
    kind TEXT, key TEXT, value DOUBLE PRECISION, lo DOUBLE PRECISION, hi DOUBLE PRECISION, n_events INT,
    PRIMARY KEY (kind, key)
);

CREATE TABLE IF NOT EXISTS live_conditions (
    ts TIMESTAMPTZ PRIMARY KEY, rain_mm REAL, visibility_m REAL, temp_c REAL, source TEXT
);

CREATE TABLE IF NOT EXISTS live_traffic (
    segment_id BIGINT, ts TIMESTAMPTZ, current_speed REAL, free_flow_speed REAL, congestion_ratio REAL,
    PRIMARY KEY (segment_id, ts)
);

-- Crowdsourced reports: 'pending' until a moderator approves; never used by the model until approved
CREATE TABLE IF NOT EXISTS user_reports (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ DEFAULT now(),
    kind          TEXT NOT NULL CHECK (kind IN ('accident','hazard','pothole','poor_lighting','waterlogging')),
    description   TEXT,
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    reporter_hash TEXT,                 -- salted hash of IP, never the raw IP
    segment_id    BIGINT,
    geom          GEOMETRY(Point, 4326)
);
CREATE INDEX IF NOT EXISTS idx_user_reports_geom ON user_reports USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_user_reports_status ON user_reports (status, created_at);

-- Safety interventions (speed breaker, lighting...) for before/after evaluation
CREATE TABLE IF NOT EXISTS interventions (
    id SERIAL PRIMARY KEY,
    segment_id BIGINT REFERENCES road_segments(segment_id) ON DELETE CASCADE,
    kind TEXT, installed_on DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS data_quality_log (
    id BIGSERIAL PRIMARY KEY, run_at TIMESTAMPTZ DEFAULT now(),
    check_name TEXT, passed BOOLEAN, level TEXT, detail TEXT
);

CREATE TABLE IF NOT EXISTS risk_snapshots (
    id BIGSERIAL PRIMARY KEY, taken_at TIMESTAMPTZ DEFAULT now(),
    model_version TEXT, hist JSONB, psi DOUBLE PRECISION
);
