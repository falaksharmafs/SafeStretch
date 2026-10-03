# Step-by-step integration guide

Do the steps in order. Each ends with a **check** so you know it worked before moving on.
Everything runs locally first; deployment is Stage 5.

## Stage 0 - Prerequisites
Python 3.11, Docker, Git. `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
`cp .env.example .env` and set `PLACE_NAME` (keep it to ONE city).
**Check:** `docker compose version` prints a version.

## Stage 1 - Database with migrations
1. `make up` (PostGIS + pgRouting container).
2. `make migrate` - applies `migrations/001..003` once each, tracked in `schema_migrations`.
**Check:** `docker exec -it roadrisk-db psql -U postgres roadrisk -c '\dt'` lists `segment_risk`, `user_reports`, `risk_multipliers`...
If `CREATE EXTENSION pgrouting` fails, your image has no pgRouting: use the one in `docker-compose.yml`.

## Stage 2 - Base data and the original model
1. `make setup` - OSM roads, POIs, static features, routing nodes.
2. Load accidents. Either
   * real data: `python -m src.etl.load_accidents --file data/raw/x.csv --lat-col ... --lon-col ... --date-col ... --severity-col ...`, or
   * demo: `make pipeline-synth` (synthetic - results are NOT findings).
3. `python -m src.etl.load_weather` then `python -m src.run_sql 03_snap_and_counts.sql`.
4. `python -m src.validation` - the data-quality gate. Fix anything marked ERROR first.
5. `make train` - hotspots, Empirical-Bayes ranking, multipliers, calibrated ML model.
**Check:** `reports/metrics.json` exists; `SELECT COUNT(*) FROM segment_risk, segment_eb, risk_multipliers;` all non-zero.
Look at `calibration.reliability_calibrated_test` - predicted and observed should roughly match per bin.

## Stage 3 - Make it realistic (what each piece does)
| Piece | File | Run |
|---|---|---|
| Exposure-adjusted EB black-spot ranking | `src/models/empirical_bayes.py` | `python -m src.models.empirical_bayes` (add `--traffic-csv` with `segment_id,aadt` when you have counts) |
| Hour-of-day and rain multipliers | `src/models/multipliers.py` | `python -m src.models.multipliers` |
| Calibration + uncertainty | inside `train.py` | automatic (Brier score + reliability bins) |
| Intervention before/after | `src/models/intervention_eval.py` | `--load data/interventions.csv` then run again without it |
**Check:** compare `eb_rank` and `risk_rank` for the top 50 segments - they should overlap but not be identical. Explain the differences in your README (regression to the mean, exposure).

## Stage 4 - Make it live
1. `make live` - pulls current weather, refreshes `live_risk`.
2. (Optional) `export TOMTOM_KEY=...` for congestion context.
3. `make api` and open http://localhost:8000/docs. Try `/risk?lat=..&lon=..` and `/route?...`.
4. Tiles: `docker compose --profile app up -d tiles`, then open http://localhost:8000/app/ (set `window.TILES_URL` if tiles are elsewhere).
5. Scheduler: `python -m src.live.scheduler` (weather every 30 min, monthly retrain via `RETRAIN_CRON`).
**Check:** `/risk` returns `live.rain` matching real weather; `/route` returns two features (`fastest`, `safest`).

Live design note: the live score is `calibrated base probability x hour multiplier x rain multiplier` - a RELATIVE index, not a probability. Traffic is context only until you have history to learn its effect. Say this in interviews.

## Stage 5 - Deploy
**Option A - one VPS (simplest, supports pgRouting):**
1. Set secrets in `.env`: `POSTGRES_PASSWORD, API_KEYS, ADMIN_KEY, HASH_SALT, TOMTOM_KEY`.
2. `docker compose --profile app up -d --build`; put Caddy/Nginx with HTTPS in front of ports 8000 and 8501.
3. Load data once: `docker compose run --rm scheduler python -m src.etl.load_roads` (and the other Stage 2 commands).

**Option B - managed:** managed Postgres with PostGIS **and pgRouting** (check availability; Supabase offers both), then deploy `render.yaml` and set `DATABASE_URL`. If your host lacks pgRouting, keep the DB on a VPS or compute routes with networkx.

**CI/CD (GitHub):** push the repo; `ci.yml` runs lint + migrations + tests on a PostGIS service. Add secrets `DATABASE_URL`, `PLACE_NAME` (retrain), `RENDER_API_HOOK`, `RENDER_DASHBOARD_HOOK` (deploy). `retrain.yml` runs monthly and aborts if validation fails.

## Stage 6 - Monitor and operate
* `docker compose --profile app --profile monitoring up -d` -> Prometheus :9090, Grafana :3000 (import a FastAPI dashboard, query `http_request_duration_seconds`).
* Drift: each training run stores a score histogram and PSI in `risk_snapshots` (>0.25 = investigate).
* Experiments: `mlflow ui` shows every run; roll back by copying `models/model_<version>.joblib` over `models/latest.joblib` and re-running scoring, or re-running `train` after fixing data.
* Moderation: `GET /admin/reports/pending` then `POST /admin/reports/{id}` with `{"status":"approved"}` and the admin key.

## Troubleshooting
* **`route` 404 "No road within 500 m"** - run `python -m src.run_sql 05_routing_nodes.sql` after (re)loading roads.
* **`live_risk` empty / REFRESH fails** - run `make train` first (it fills `segment_risk`).
* **pg_tileserv shows no layer** - the `risk_tiles` view needs migrations applied and `segment_risk` populated; layer name is `public.risk_tiles`.
* **Very few positives warning in training** - too little accident data for one city/quarter split; widen the study area or the date range.
* **Rain multipliers all 1.0** - weather not loaded for the accident dates.
