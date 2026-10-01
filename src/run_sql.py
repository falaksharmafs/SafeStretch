"""Usage: python -m src.run_sql 01_schema.sql"""
import sys
from .db import run_sql_file

if __name__ == "__main__":
    for f in sys.argv[1:]:
        run_sql_file(f)
        print(f"ran {f}")
