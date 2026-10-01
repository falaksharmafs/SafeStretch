import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/roadrisk")
PLACE_NAME = os.getenv("PLACE_NAME", "Indore, Madhya Pradesh, India")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
SNAP_MAX_M = float(os.getenv("SNAP_MAX_M", "50"))       # max distance to snap an accident to a road
GRID_DEG = float(os.getenv("GRID_DEG", "0.02"))         # ~2 km blocks for spatial cross-validation
POI_RADIUS_M = 200

SQL_DIR = ROOT / "sql"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
