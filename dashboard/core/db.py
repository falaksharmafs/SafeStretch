import pandas as pd
from sqlalchemy import text

from src.db import get_engine   # reuses DATABASE_URL from your .env (port 5433 on your setup)


def read(sql: str, **params) -> pd.DataFrame:
    with get_engine().connect() as con:
        return pd.read_sql(text(sql), con, params=params or None)


def scalar(sql: str, default=None, **params):
    df = read(sql, **params)
    return default if df.empty or pd.isna(df.iloc[0, 0]) else df.iloc[0, 0]
