"""Apply versioned SQL migrations once each.  Usage: python -m src.migrate"""
from .config import MIGRATIONS_DIR
from .db import get_engine, run_sql_file


def main():
    eng = get_engine()
    with eng.begin() as con:
        con.exec_driver_sql("CREATE TABLE IF NOT EXISTS schema_migrations "
                            "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())")
        done = {r[0] for r in con.exec_driver_sql("SELECT version FROM schema_migrations")}
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if f.name in done:
            continue
        print(f"applying {f.name}")
        run_sql_file(f.name, MIGRATIONS_DIR)
        with eng.begin() as con:
            con.exec_driver_sql("INSERT INTO schema_migrations (version) VALUES (%s)", (f.name,))
    print("migrations up to date")


if __name__ == "__main__":
    main()
