#!/usr/bin/env bash
# Full pipeline. Steps marked [REAL] / [SYNTH] are alternatives - pick one accident source.
set -euo pipefail

docker compose up -d db && sleep 8
python -m src.run_sql 01_schema.sql
python -m src.etl.load_roads
python -m src.etl.load_poi
python -m src.run_sql 02_static_features.sql

# [SYNTH] test the pipeline with generated data (NOT real findings)
python -m src.etl.generate_synthetic_accidents --n 30000
python -m src.etl.load_accidents --file data/raw/synthetic_accidents.csv --preset synthetic

# [REAL] replace the two lines above with your dataset, e.g.:
# python -m src.etl.load_accidents --file data/raw/my_accidents.csv --lat-col Lat --lon-col Lon \
#        --date-col "Date" --time-col "Time" --severity-col Severity --dayfirst

python -m src.etl.load_weather            # optional but recommended (needs internet)
python -m src.run_sql 03_snap_and_counts.sql
python -m src.models.hotspots
python -m src.models.train
streamlit run app/streamlit_app.py
