"""Introspection so the dashboard adapts to whatever your database currently contains."""
import streamlit as st

from .db import read, scalar


@st.cache_data(ttl=300, show_spinner=False)
def columns(table: str) -> tuple:
    """Column names of a table, view or materialized view in public (empty tuple if it does not exist)."""
    df = read("SELECT a.attname AS c FROM pg_attribute a WHERE a.attrelid = to_regclass(:t) "
              "AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum", t=f"public.{table}")
    return tuple(df.c)


def has_table(table: str) -> bool:
    return len(columns(table)) > 0


def geom_col(table: str):
    cols = columns(table)
    return next((c for c in ("geom", "geometry") if c in cols), None)


@st.cache_data(ttl=120, show_spinner=False)
def row_count(table: str) -> int:
    return int(scalar(f"SELECT COUNT(*) FROM {table}", 0)) if has_table(table) else 0
