# SafeStretch dashboard (Stage 1)

A map-first, dark/light "command center" UI that reads your **existing** PostGIS tables. It does not modify the
database, the loaders, the trainer or your current `app/streamlit_app.py` (which keeps working).

## Run (Windows, from the project root, venv active)
```
pip install -r dashboard\requirements-dashboard.txt
streamlit run dashboard\app.py
```
Uses `DATABASE_URL` from your `.env` (port 5433). Theme: top-right ⋮ menu → Settings → Theme (dark is the default).

## Pages in this drop
| Page | What it does |
|---|---|
| Overview | KPI strip, hero map, priority segments, risk bands, quarterly accidents, severity mix |
| Risk Map | layered map, filters, click-to-inspect panel with SHAP drivers, ranking table synced both ways, road search |
| Hotspots | KPIs, hotspot map, per-hotspot detail with the accidents inside it, ranking table |
| Analytics | distribution, ranking, road type / area, hour-of-day (95% bands), rain vs dry, severity |
| Model | validation vs baseline, calibration, Empirical-Bayes comparison, explainability |
| Data Health | green/amber/red checks with reasons, service status |

## Works on your baseline today
Everything reads tables you already have. Anything that needs the upgraded project shows "Not available" and lights up
automatically once it exists: calibration (`metrics.json → calibration`), EB comparison (`segment_eb`), feature importance
(`models/latest.joblib`), live weather (`live_conditions`), validation log (`data_quality_log`).

## Data-integrity rules built in
Nothing is invented: missing values show N/A; trends appear only when two complete quarters exist; the model score is
labelled *uncalibrated*; no accuracy percentage; synthetic data is flagged in the header and on every analytics page;
hotspot "roads within ε / top road percentile" are labelled as derived, not stored membership.

## Not in this drop (Stages 2-3)
Live Risk, Route Planner, Interventions, Reports/moderation, MLOps monitoring, MapLibre/pg_tileserv frontend. They depend
on the upgraded migrations/services, so they come after those are integrated and verified.
