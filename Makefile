.PHONY: help up down migrate setup pipeline-synth live train api dashboard test lint stack monitoring

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1 | tr '\n' ' '; echo

up:            ## start PostGIS + pgRouting
	docker compose up -d db

down:
	docker compose --profile app --profile monitoring down

migrate:       ## apply versioned SQL migrations
	python -m src.migrate

setup: up migrate   ## load roads/POIs and static features for PLACE_NAME
	python -m src.etl.load_roads
	python -m src.etl.load_poi
	python -m src.run_sql 02_static_features.sql 05_routing_nodes.sql

pipeline-synth: ## DEMO ONLY: synthetic accidents -> full model build
	python -m src.etl.generate_synthetic_accidents --n 30000
	python -m src.etl.load_accidents --file data/raw/synthetic_accidents.csv --preset synthetic
	python -m src.etl.load_weather
	python -m src.run_sql 03_snap_and_counts.sql
	python -m src.validation
	$(MAKE) train live

train:         ## hotspots, EB ranking, multipliers, ML model
	python -m src.models.hotspots
	python -m src.models.empirical_bayes
	python -m src.models.multipliers
	python -m src.models.train

live:          ## fetch live weather and refresh live_risk
	python -m src.live.weather_live
	python -m src.live.refresh

api:
	uvicorn api.main:app --reload --port 8000

dashboard:
	streamlit run app/streamlit_app.py

stack:         ## everything in Docker
	docker compose --profile app up -d --build

monitoring:
	docker compose --profile app --profile monitoring up -d

test:
	pytest -q

lint:
	ruff check .
