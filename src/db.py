from functools import lru_cache
from sqlalchemy import create_engine
from .config import DATABASE_URL, SQL_DIR, TIMEZONE, SNAP_MAX_M, POI_RADIUS_M


@lru_cache
def get_engine():
    return create_engine(DATABASE_URL, future=True)


def run_sql_file(name: str) -> None:
    """Run a multi-statement .sql file from /sql, filling {{PLACEHOLDERS}} from config."""
    text = (SQL_DIR / name).read_text()
    for key, val in {"SNAP_MAX_M": SNAP_MAX_M, "POI_RADIUS_M": POI_RADIUS_M, "TIMEZONE": TIMEZONE}.items():
        text = text.replace("{{" + key + "}}", str(val))
    raw = get_engine().raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(text)
        raw.commit()
    finally:
        raw.close()
